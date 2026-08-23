# -*- coding: utf-8 -*-
import logging
from typing import Dict, Any, Optional

from option_program.strategy.common import AtomicBudgetManager, TradingDateResetHelper, ExecutionCostCalculator, WallClockTimer
from option_program.strategy.strategy_contract import StrategyContract

logger = logging.getLogger(__name__)


class Track7(StrategyContract):
    """
    [Track7] Volatility Arbitrage / Skew Trading & Weekly Tail Insurance
    - 자본 배분: 매주 상장 후 조건 만족 시 +2.0% 동적 부여
    - 주요 업그레이드 메커니즘:
      1. 위클리 옵션 개장 첫날(is_new_week_start) 지정가 분할 예약 매수 큐(Limit Queue) 배치. (15:15 미체결 취소 및 익일 동적 재배치)
      2. Call/Put IV Skew 괴리(|skew| >= 3.0) 탐지 시 1차 지정가 예약 진입 -> 타임아웃 미체결 시 2차 예비 시장가(Fallback) 전환.
      3. 지수 급변 후 1분/3분/5분/10분 MA 교차 및 지지/저항선 기반 선제적 지정가 익절 예약(Preemptive Limit Take-Profit).
      4. 금요일 15:00 1단계 지정가 선제 컷오프 -> 15:15 미체결분 2단계 예비 시장가(Fallback Market) 강제 청산.
    """

    def __init__(self, config: Dict[str, Any]):
        self.params = config.get("strategies", {}).get("strategy_7", {}).get("params", {})
        # 등가격 ATM 대비 옵션 격리 거리 (행사가 격리 포인트)
        self.strike_offset = self.params.get("strike_offset", 15.0)
        # 매수 계약수
        self.insurance_qty = self.params.get("insurance_qty", 1)
        # 만기 청산 모드 (기본: D-0 CUTOFF 만기 당일 15:15 원자적 100% Flat / D-4: 금요일 당일 사전 청산)
        self.expiry_mode = self.params.get("expiry_mode", "D-0 CUTOFF")

        self.skew_active: bool = False
        self.skew_limit_pending: bool = False
        self.date_reset_helper = TradingDateResetHelper()
        self.budget_manager = AtomicBudgetManager(initial_budget=0.0)
        self.reset_state()
        logger.info(f"Volatility Arbitrage & Weekly Insurance Strategy (Track7) Initialized with expiry_mode={self.expiry_mode}.")

    def reset_state(self) -> None:
        self.insurance_state: Dict[str, Any] = {
            "is_active": False,
            "bought_date": None,
            "long_put_strike": 0.0,
            "long_call_strike": 0.0,
            "premium_spent": 0.0,
            "high_watermark_intrinsic": 0.0,
            "trailing_stop_active": False,
        }
        self.skew_active = False
        self.skew_limit_pending = False

    async def evaluate_insurance_buy_async(
        self,
        current_price: float,
        budget: float,
        date_str: str,
        is_new_week_start: bool,
        active_vol: float = 1.0,
        time_str: str = "09:00:00",
    ) -> Dict[str, Any]:
        """
        [비동기 원자적 예산 차감 반영 위클리 보험 지정가 분할 큐 진입 판단]
        """
        if self.date_reset_helper.check_and_update(date_str):
            self.reset_state()

        if self.insurance_state["is_active"]:
            return {"status": "ALREADY_ACTIVE", "signals": []}

        # 15:15 미체결 분할 큐 일괄 취소 시그널
        if "15:15" <= time_str < "15:20":
            return {
                "status": "CANCEL_PENDING",
                "signals": [
                    {
                        "action": "CANCEL_PENDING_TRANCHES",
                        "reason": "15:15 위클리 지정가 분할 큐 미체결 일괄 취소",
                    }
                ],
            }

        if not is_new_week_start:
            return {"status": "NOT_NEW_WEEK", "signals": []}

        vol_scale = 0.5 if active_vol < 1.0 else 1.0
        estimated_cost = 1.4 * 250000.0 * self.insurance_qty * vol_scale

        self.budget_manager.set_budget(budget)
        success, _ = await self.budget_manager.try_deduct(estimated_cost)
        if not success:
            return {"status": "NO_BUDGET", "signals": []}

        signals = []
        atm_strike = round(current_price / 2.5) * 2.5
        long_put = atm_strike - self.strike_offset
        long_call = atm_strike + self.strike_offset

        self.insurance_state["is_active"] = True
        self.insurance_state["bought_date"] = date_str
        self.insurance_state["long_put_strike"] = long_put
        self.insurance_state["long_call_strike"] = long_call
        self.insurance_state["premium_spent"] = estimated_cost

        logger.warning("[WEEKLY INSURANCE TRIGGER] 위클리 옵션 지정가 분할 큐 양매수 구축 (호가창 Mid-Price 연동).")
        signals.append({
            "action": "BUY_LIMIT_WEEKLY_INSURANCE",
            "reason": "New trading week started. Setting up weekly limit queue strangle protection via Mid-Price Adapter.",
            "put_strike": long_put,
            "call_strike": long_call,
            "pricing_mode": "MID_PRICE_OFFSET",
            "limit_offset_ticks": 1,
            "fallback_market_timeout_sec": 5.0,
            "qty": self.insurance_qty,
            "cost": estimated_cost,
        })
        return {"status": "TRIGGERED", "signals": signals}

    def evaluate_insurance_buy(
        self,
        current_price: float,
        budget: float,
        date_str: str,
        is_new_week_start: bool,
        active_vol: float = 1.0,
        time_str: str = "09:00:00",
    ) -> Dict[str, Any]:
        """
        [동기 방식 호환 주간 상장 첫날 위클리 보험 지정가 분할 큐 진입 판단]
        """
        if self.date_reset_helper.check_and_update(date_str):
            self.reset_state()

        if self.insurance_state["is_active"]:
            return {"status": "ALREADY_ACTIVE", "signals": []}

        if "15:15" <= time_str < "15:20":
            return {
                "status": "CANCEL_PENDING",
                "signals": [
                    {
                        "action": "CANCEL_PENDING_TRANCHES",
                        "reason": "15:15 위클리 지정가 분할 큐 미체결 일괄 취소",
                    }
                ],
            }

        if not is_new_week_start:
            return {"status": "NOT_NEW_WEEK", "signals": []}

        vol_scale = 0.5 if active_vol < 1.0 else 1.0
        estimated_cost = 1.4 * 250000.0 * self.insurance_qty * vol_scale
        if budget < estimated_cost:
            return {"status": "NO_BUDGET", "signals": []}

        signals = []
        atm_strike = round(current_price / 2.5) * 2.5
        long_put = atm_strike - self.strike_offset
        long_call = atm_strike + self.strike_offset

        self.insurance_state["is_active"] = True
        self.insurance_state["bought_date"] = date_str
        self.insurance_state["long_put_strike"] = long_put
        self.insurance_state["long_call_strike"] = long_call
        self.insurance_state["premium_spent"] = estimated_cost

        logger.warning("[WEEKLY INSURANCE TRIGGER] 위클리 옵션 지정가 분할 큐 양매수 구축 (호가창 Mid-Price 연동).")
        signals.append({
            "action": "BUY_LIMIT_WEEKLY_INSURANCE",
            "reason": "New trading week started. Setting up weekly limit queue strangle protection via Mid-Price Adapter.",
            "put_strike": long_put,
            "call_strike": long_call,
            "pricing_mode": "MID_PRICE_OFFSET",
            "limit_offset_ticks": 1,
            "fallback_market_timeout_sec": 5.0,
            "qty": self.insurance_qty,
            "cost": estimated_cost,
        })
        return {"status": "TRIGGERED", "signals": signals}

    def evaluate_skew_arbitrage(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        [IV Skew 괴리 탐지 1차 지정가 + 2차 예비 시장가 Fallback 차익거래 로직]
        """
        date_str = market_data.get("date_str", "UNKNOWN")
        if self.date_reset_helper.check_and_update(date_str):
            self.reset_state()

        raw_pnl = (
            market_data.get("track7_current_pnl")
            if market_data.get("track7_current_pnl") is not None
            else market_data.get("current_pnl", 0.0)
        )
        raw_fees = (
            market_data.get("track7_total_fees")
            if market_data.get("track7_total_fees") is not None
            else market_data.get("total_fees", 0.0)
        )
        current_pnl: float = float(raw_pnl or 0.0)
        total_fees: float = float(raw_fees or 0.0)

        call_iv = float(market_data.get("call_iv", 0.0))
        put_iv = float(market_data.get("put_iv", 0.0))
        skew = put_iv - call_iv

        signals = []

        # 1. Skew 괴리 이탈 시 1차 지정가 예약 진입 (|skew| >= 3.0)
        if not self.skew_active:
            if abs(skew) >= 3.0:
                self.skew_active = True
                self.skew_limit_pending = True
                action_type = (
                    "LONG_PUT_SHORT_CALL" if skew > 0 else "LONG_CALL_SHORT_PUT"
                )
                signals.append({
                    "action": "ENTER_SKEW_ARB_LIMIT",
                    "type": action_type,
                    "skew": skew,
                    "reason": f"IV Skew 괴리({skew:.2f}) 감지. 1차 지정가 예약 진입 투입.",
                    "qty": 1,
                })
                return {"status": "SKEW_LIMIT_PENDING", "signals": signals}

        # 2. 보유 및 펜딩 상태 관리
        else:
            # 지정가 미체결 타임아웃 발생 시 2차 예비 시장가 전환 (Fallback)
            if self.skew_limit_pending and market_data.get(
                "skew_limit_timeout", False
            ):
                self.skew_limit_pending = False
                signals.append({
                    "action": "ENTER_SKEW_ARB_FALLBACK_MARKET",
                    "skew": skew,
                    "reason": "지정가 미체결 타임아웃 발생. 2차 예비 시장가(Fallback) 전환 체결.",
                    "qty": 1,
                })
                return {"status": "SKEW_FALLBACK_EXECUTED", "signals": signals}

            # Skew 왜곡 심화 (|skew| > 8.0) 시 손절
            if abs(skew) > 8.0:
                self.skew_active = False
                self.skew_limit_pending = False
                signals.append({
                    "action": "CLOSE_SKEW_ARB_STOP_LOSS",
                    "skew": skew,
                    "reason": f"IV Skew 왜곡 심화 ({skew:.2f} > 8.0). 손절 가드 집행.",
                    "qty": 1,
                })
                return {"status": "SKEW_STOP_LOSS", "signals": signals}

            # Skew 정상 회귀 (|skew| <= 0.5) 시 1차 지정가 청산
            if abs(skew) <= 0.5:
                self.skew_active = False
                self.skew_limit_pending = False
                reason_str = f"IV Skew 정상 회귀({skew:.2f}) 1차 지정가 청산."
                signals.append({
                    "action": "CLOSE_SKEW_ARB_LIMIT",
                    "skew": skew,
                    "reason": reason_str,
                    "qty": 1,
                })
                return {"status": "SKEW_CLOSED", "signals": signals}

        return {"status": "HOLD", "signals": []}

    def evaluate_expiry_cutoff(
        self, time_str: str, is_expiry_day: Optional[bool] = None, is_week_end: bool = False, date_str: str = "UNKNOWN"
    ) -> Dict[str, Any]:
        """
        [위클리 옵션 최종 거래일/만기 당일 15:00 지정가 우선 컷오프 및 15:15 예비 시장가 청산(Fallback) 판단]
        - 공휴일 전일 당겨진 만기일 및 목요/월요 위클리 옵션 만기일에 정확히 연동.
        - expiry_mode == 'D-4'인 경우 금요일 당일 사전 청산 지원.
        """
        if self.date_reset_helper.check_and_update(date_str):
            self.reset_state()

        if not self.insurance_state["is_active"]:
            return {"status": "INACTIVE", "signals": []}

        # D-4 모드: 금요일(진입 당일) 장 마감 직전 사전 청산 처리
        if self.expiry_mode == "D-4" and self.insurance_state.get("bought_date") == date_str and time_str >= "15:00:00":
            signals = [{
                "action": "CLOSE_WEEKLY_INSURANCE_PREEMPTIVE_D4",
                "reason": "expiry_mode=D-4 설정에 따른 금요일 장 마감 전 사전 청산",
                "put_strike": self.insurance_state["long_put_strike"],
                "call_strike": self.insurance_state["long_call_strike"],
                "qty": self.insurance_qty,
            }]
            self.reset_state()
            return {"status": "D4_PREEMPTIVE_CLOSED", "signals": signals}

        # is_expiry_day 매개변수가 우선 적용되며, 기존 is_week_end 하위 호환 지원
        expiry_active = is_expiry_day if is_expiry_day is not None else is_week_end

        if expiry_active:
            # 1단계 (15:00): 유리한 지정가 예약 청산 선제 투입
            if "15:00:00" <= time_str < "15:15:00":
                return {
                    "status": "CUTOFF_LIMIT_PENDING",
                    "signals": [{
                        "action": "CLOSE_WEEKLY_INSURANCE_LIMIT",
                        "reason": "위클리 옵션 최종 거래일(만기일 목요일) 15:00 지정가 우선 청산 선제 투입",
                        "put_strike": self.insurance_state["long_put_strike"],
                        "call_strike": self.insurance_state["long_call_strike"],
                        "qty": self.insurance_qty,
                    }],
                }

            # 2단계 (15:15): 미체결분 2단계 예비 시장가(Fallback) 100% 강제 청산
            if time_str >= "15:15:00":
                signals = []
                logger.critical(
                    "[WEEKLY INSURANCE CUTOFF] 위클리 옵션 만기일 15:15 미체결분 2단계 예비 시장가(Fallback) 강제 청산 발동!"
                )
                signals.append({
                    "action": "CLOSE_WEEKLY_INSURANCE_FALLBACK_MARKET",
                    "reason": "위클리 옵션 만기일 15:15 정산 시점 미체결 잔여분 예비 시장가(Fallback Market) 강제 청산",
                    "put_strike": self.insurance_state["long_put_strike"],
                    "call_strike": self.insurance_state["long_call_strike"],
                    "qty": self.insurance_qty,
                })
                self.reset_state()
                return {"status": "CUTOFF_FALLBACK_EXECUTED", "signals": signals}

        return {"status": "HOLD", "signals": []}

    def evaluate_take_profit(
        self,
        current_price: float,
        ma_cross_signal: bool = False,
        resistance_break: bool = False,
        active_vol: float = 1.0,
    ) -> Dict[str, Any]:
        """
        [2단계 하이브리드 익절: VKOSPI 최소 이익선 돌파 -> High Watermark 트레일링 스탑]
        """
        if not self.insurance_state["is_active"]:
            return {"status": "INACTIVE", "signals": []}

        put_k = self.insurance_state["long_put_strike"]
        call_k = self.insurance_state["long_call_strike"]
        qty = self.insurance_qty

        put_intrinsic = max(0.0, put_k - current_price) * 250000.0 * qty
        call_intrinsic = max(0.0, current_price - call_k) * 250000.0 * qty
        total_intrinsic = put_intrinsic + call_intrinsic
        spent = self.insurance_state.get("premium_spent", 350000.0)

        # 1단계: VKOSPI 변동성 연동 최소 이익선 산정 (기본 1.5배)
        min_multiplier = 1.5 if active_vol < 1.0 else 2.0

        # 최소 이익선 돌파 시 트레일링 스탑 모드 가동
        if total_intrinsic >= spent * min_multiplier or ma_cross_signal or resistance_break:
            self.insurance_state["trailing_stop_active"] = True

        # 2단계: 트레일링 스탑 가동 중 최고점 대비 3단계 동적 스케일링 반락선 지정가 예약 큐 실시간 선제 배치
        if self.insurance_state["trailing_stop_active"]:
            prev_high = self.insurance_state.get("high_watermark_intrinsic", 0.0)
            current_high = max(prev_high, total_intrinsic)

            pnl_ratio = current_high / max(1.0, spent)
            if pnl_ratio >= 2.0:
                trailing_ratio = 0.90
                step_name = "3단계(+100% 이상 잭팟 -10% 타이트)"
            elif pnl_ratio >= 1.3:
                trailing_ratio = 0.88
                step_name = "2단계(+30%~+100% -12% 조임)"
            else:
                trailing_ratio = 0.85
                step_name = "1단계(+30% 미만 -15% 유지)"

            stop_trigger_price = current_high * trailing_ratio

            if current_high > 0 and total_intrinsic <= stop_trigger_price:
                signals = [{
                    "action": "TAKE_PROFIT_HYBRID_TRAILING_STOP",
                    "reason": f"Weekly High Watermark (KRW {current_high:,.0f}) 대비 {step_name} 반락. 트레일링 스탑 지정가 익절 완료.",
                    "realized_amount": total_intrinsic,
                    "put_strike": put_k,
                    "call_strike": call_k,
                    "qty": qty,
                }]
                self.reset_state()
                return {
                    "status": "PROFIT_TAKEN_TRAILING_STOP",
                    "signals": signals,
                    "realized": total_intrinsic,
                }

            # 보완점 ②: 최고점 1.0% 이상 의미 있는 상승 시만 지정가 예약 큐 갱신 (Throttling)
            if prev_high == 0.0 or current_high >= prev_high * 1.01:
                self.insurance_state["high_watermark_intrinsic"] = current_high
                return {
                    "status": "TRAILING_STOP_LIMIT_QUEUE_UPDATED",
                    "signals": [{
                        "action": "TAKE_PROFIT_PREEMPTIVE_TRAILING_LIMIT",
                        "pricing_mode": "PREEMPTIVE_STOP_LIMIT_QUEUE",
                        "stop_trigger_price": stop_trigger_price,
                        "limit_offset_ticks": 2,  # 갭다운 방어 2틱 버퍼
                        "fallback_market_timeout_sec": 2.0,
                        "reason": f"High Watermark (KRW {current_high:,.0f}) 1% 이상 갱신. {step_name} 지정가 예약 큐 선제 배치",
                        "put_strike": put_k,
                        "call_strike": call_k,
                        "qty": qty,
                    }]
                }

        return {"status": "HOLD", "signals": []}

