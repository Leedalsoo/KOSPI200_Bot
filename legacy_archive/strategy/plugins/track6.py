# -*- coding: utf-8 -*-
import logging
from typing import Dict, Any, Optional
from strategy.common import TradingDateResetHelper, AtomicBudgetManager, ExecutionCostCalculator, WallClockTimer
from strategy.strategy_contract import StrategyContract

logger = logging.getLogger(__name__)

class Track6(StrategyContract):
    """
    [Track6] 데일리 테일 보험 봇 (Track 6 Daily 0DTE)
    - 자본 배분: 매일 변동성 조건 만족 시 +2.0% 동적 부여
    - HFT 슬리피지 극복 명세:
      1. 변동성 폭발(active_vol >= base_vol * 1.3) 감지 시 0.5초 단위 호가 추격(Sub-second Escalation) 및 IOC 하이브리드 지정가 큐 투입.
      2. 호가창 스프레드가 3틱 이상 벌어지거나 비유동성 공백 시 진입 차단(Liquidity Depth Guard).
      3. 15:15 미체결 분할 큐 일괄 취소(CANCEL)로 당일 마감 오버나잇 위험 원천 차단.
      4. 15:00 1단계 지정가 선제 컷오프 -> 15:15 2단계 미체결분 예비 시장가(Fallback Market) 강제 청산.
    """
    def __init__(self, config: Dict[str, Any]):
        self.params = config.get("strategies", {}).get("strategy_6", {}).get("params", {})
        # 변동성 경보 임계 배율 (1.3배)
        self.vol_trigger_multiplier = self.params.get("vol_trigger_multiplier", 1.3)
        # 등가격 ATM 대비 옵션 격리 거리 (행사가 격리 포인트)
        self.strike_offset = self.params.get("strike_offset", 12.5)
        # 매수할 1방향당 계약수
        self.insurance_qty = self.params.get("insurance_qty", 1)
        
        self.date_reset_helper = TradingDateResetHelper()
        self.budget_manager = AtomicBudgetManager(initial_budget=0.0)
        self.reset_state()
        logger.info("Daily Tail Insurance Bot (Track6) Initialized.")

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

    def evaluate_take_profit(self, current_price: float, active_vol: float = 1.0, time_str: str = "09:00:00") -> Dict[str, Any]:
        """
        [2단계 하이브리드 익절: VKOSPI 최소 이익선 돌파 -> High Watermark 트레일링 스탑]
        - 보완점 ①: 갭다운 방어 2틱 지정가 버퍼 오프셋 (limit_offset_ticks: 2)
        - 보완점 ②: 최고점 1.0% 이상 의미 있는 상승 시만 갱신 Throttling
        - 보완점 ③: 15:12:00 이후 트레일링 스탑 락다운 (15:15 컷오프 우선보장)
        """
        if not self.insurance_state["is_active"]:
            return {"status": "INACTIVE", "signals": []}

        # 보완점 ③: 15:12:00 이후에는 15:15 컷오프 우선보장을 위해 트레일링 스탑 신호 잠금
        if time_str >= "15:12:00":
            return {"status": "LOCKDOWN_FOR_EXPIRY", "signals": []}

        put_k = self.insurance_state["long_put_strike"]
        call_k = self.insurance_state["long_call_strike"]
        qty = self.insurance_qty

        put_intrinsic = max(0.0, put_k - current_price) * 250000.0 * qty
        call_intrinsic = max(0.0, current_price - call_k) * 250000.0 * qty
        total_intrinsic = put_intrinsic + call_intrinsic
        spent = self.insurance_state.get("premium_spent", 250000.0)

        # 1단계: VKOSPI 변동성 연동 최소 이익선 산정 (기본 1.5배)
        min_multiplier = 1.5 if active_vol < 1.3 else 2.0
        
        # 최소 이익선 돌파 시 트레일링 스탑 가동
        if total_intrinsic >= spent * min_multiplier:
            self.insurance_state["trailing_stop_active"] = True

        # 2단계: 트레일링 스탑 가동 중 최고점 대비 3단계 동적 스케일링 반락선 지정가 예약 큐 실시간 선제 배치
        if self.insurance_state["trailing_stop_active"]:
            prev_high = self.insurance_state.get("high_watermark_intrinsic", 0.0)
            current_high = max(prev_high, total_intrinsic)

            # 3단계 동적 스케일링 반락 비율 결정
            # 1단계 (PnL < 1.3배/+30% 미만): -15% (0.85)
            # 2단계 (1.3배 <= PnL < 2.0배/+30%~+100%): -12% (0.88)
            # 3단계 (PnL >= 2.0배/+100% 이상 잭팟): -10% (0.90)
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
                    "reason": f"0DTE High Watermark (KRW {current_high:,.0f}) 대비 {step_name} 반락. 트레일링 스탑 지정가 익절 완료.",
                    "realized_amount": total_intrinsic,
                    "put_strike": put_k,
                    "call_strike": call_k,
                    "qty": qty
                }]
                self.reset_state()
                return {"status": "PROFIT_TAKEN_TRAILING_STOP", "signals": signals, "realized": total_intrinsic}

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
                        "qty": qty
                    }]
                }

        return {"status": "HOLD", "signals": []}

    def evaluate_expiry_cutoff(self, time_str: str, date_str: str = "UNKNOWN") -> Dict[str, Any]:
        """
        [15:00 지정가 선제 컷오프 & 15:15 예비 시장가 강제 청산(Fallback) 판단]
        """
        if self.date_reset_helper.check_and_update(date_str):
            self.reset_state()

        if not self.insurance_state["is_active"]:
            return {"status": "INACTIVE", "signals": []}

        # 1단계 (15:00): 유리한 지정가 예약 청산 선제 투입
        if "15:00:00" <= time_str < "15:15:00":
            return {
                "status": "CUTOFF_LIMIT_PENDING",
                "signals": [{
                    "action": "CLOSE_DAILY_INSURANCE_LIMIT",
                    "reason": "15:00 데일리 지정가 우선 청산 선제 투입",
                    "put_strike": self.insurance_state["long_put_strike"],
                    "call_strike": self.insurance_state["long_call_strike"],
                    "qty": self.insurance_qty
                }]
            }

        # 2단계 (15:15): 미체결분 2단계 예비 시장가(Fallback) 100% 강제 청산
        if time_str >= "15:15:00":
            signals = []
            logger.critical("🔥 [DAILY INSURANCE CUTOFF] 15:15 미체결분 2단계 예비 시장가(Fallback) 강제 청산 발동!")
            signals.append({
                "action": "CLOSE_DAILY_INSURANCE_FALLBACK_MARKET",
                "reason": "15:15 당일 정산 시점 미체결 잔여분 예비 시장가(Fallback Market) 강제 청산",
                "put_strike": self.insurance_state["long_put_strike"],
                "call_strike": self.insurance_state["long_call_strike"],
                "qty": self.insurance_qty
            })
            self.reset_state()
            return {"status": "CUTOFF_FALLBACK_EXECUTED", "signals": signals}

        return {"status": "HOLD", "signals": []}

    async def evaluate_insurance_buy_async(self, 
                                          current_price: float, 
                                          active_vol: float, 
                                          base_vol: float, 
                                          budget: float, 
                                          date_str: str,
                                          time_str: str = "09:00:00") -> Dict[str, Any]:
        """
        [비동기 원자적 예산 차감 반영 Daily 0DTE HFT 지정가 큐 진입 판단]
        """
        if self.date_reset_helper.check_and_update(date_str):
            self.reset_state()

        if self.insurance_state["is_active"]:
            return {"status": "ALREADY_ACTIVE", "signals": []}

        # 15:15 미체결 분할 큐 일괄 취소 시그널
        if "15:15" <= time_str < "15:20":
            return {
                "status": "CANCEL_PENDING",
                "signals": [{
                    "action": "CANCEL_PENDING_TRANCHES",
                    "reason": "15:15 데일리 지정가 분할 큐 미체결 일괄 취소"
                }]
            }

        estimated_cost = 1.0 * 250000.0 * self.insurance_qty

        # 1. AtomicBudgetManager 동시성 원자적 예산 차감 검증
        self.budget_manager.set_budget(budget)
        success, _ = await self.budget_manager.try_deduct(estimated_cost)
        if not success:
            return {"status": "NO_BUDGET", "signals": []}

        # 2. 내재변동성 경보 판단 (1.3배 이상 폭발)
        if active_vol >= (base_vol * self.vol_trigger_multiplier):
            signals = []
            atm_strike = round(current_price / 2.5) * 2.5
            
            long_put = atm_strike - self.strike_offset
            long_call = atm_strike + self.strike_offset
            
            self.insurance_state["is_active"] = True
            self.insurance_state["bought_date"] = date_str
            self.insurance_state["long_put_strike"] = long_put
            self.insurance_state["long_call_strike"] = long_call
            self.insurance_state["premium_spent"] = estimated_cost

            logger.warning("🚨 [DAILY INSURANCE TRIGGER] VKOSPI 변동성 경보 감지! Daily 0DTE HFT 지정가 큐 진입.")
            signals.append({
                "action": "BUY_LIMIT_DAILY_INSURANCE",
                "reason": f"Volatility spike ({active_vol:.2f} >= {base_vol*self.vol_trigger_multiplier:.2f}) detected. Buying 0DTE HFT limit queue protection.",
                "put_strike": long_put,
                "call_strike": long_call,
                "pricing_mode": "SUBSECOND_TICK_CHASER_IOC",
                "limit_offset_ticks": 1,
                "chase_interval_sec": 0.5,
                "max_chase_ticks": 3,
                "spread_guard_max_ticks": 3,
                "fallback_market_timeout_sec": 2.0,
                "qty": self.insurance_qty,
                "cost": estimated_cost
            })
            return {"status": "TRIGGERED", "signals": signals}

        # 조건 불만족 시 차감한 예산 환불
        self.budget_manager.set_budget(self.budget_manager.current_budget + estimated_cost)
        return {"status": "NO_TRIGGER", "signals": []}


    def evaluate_insurance_buy(self, 
                               current_price: float, 
                               active_vol: float, 
                               base_vol: float, 
                               budget: float, 
                               date_str: str,
                               time_str: str = "09:00:00") -> Dict[str, Any]:
        """
        [동기 방식 호환 Daily 0DTE HFT 지정가 큐 진입 판단]
        """
        if self.date_reset_helper.check_and_update(date_str):
            self.reset_state()

        if self.insurance_state["is_active"]:
            return {"status": "ALREADY_ACTIVE", "signals": []}

        if "15:15" <= time_str < "15:20":
            return {
                "status": "CANCEL_PENDING",
                "signals": [{
                    "action": "CANCEL_PENDING_TRANCHES",
                    "reason": "15:15 데일리 지정가 분할 큐 미체결 일괄 취소"
                }]
            }

        estimated_cost = 1.0 * 250000.0 * self.insurance_qty
        if budget < estimated_cost:
            return {"status": "NO_BUDGET", "signals": []}

        if active_vol >= (base_vol * self.vol_trigger_multiplier):
            signals = []
            atm_strike = round(current_price / 2.5) * 2.5
            
            long_put = atm_strike - self.strike_offset
            long_call = atm_strike + self.strike_offset
            
            self.insurance_state["is_active"] = True
            self.insurance_state["bought_date"] = date_str
            self.insurance_state["long_put_strike"] = long_put
            self.insurance_state["long_call_strike"] = long_call
            self.insurance_state["premium_spent"] = estimated_cost

            logger.warning("🚨 [DAILY INSURANCE TRIGGER] VKOSPI 변동성 경보 감지! Daily 0DTE HFT 지정가 큐 진입.")
            signals.append({
                "action": "BUY_LIMIT_DAILY_INSURANCE",
                "reason": f"Volatility spike ({active_vol:.2f} >= {base_vol*self.vol_trigger_multiplier:.2f}) detected. Buying 0DTE HFT limit queue protection.",
                "put_strike": long_put,
                "call_strike": long_call,
                "pricing_mode": "SUBSECOND_TICK_CHASER_IOC",
                "limit_offset_ticks": 1,
                "chase_interval_sec": 0.5,
                "max_chase_ticks": 3,
                "spread_guard_max_ticks": 3,
                "fallback_market_timeout_sec": 2.0,
                "qty": self.insurance_qty,
                "cost": estimated_cost
            })
            return {"status": "TRIGGERED", "signals": signals}

        return {"status": "NO_TRIGGER", "signals": []}


