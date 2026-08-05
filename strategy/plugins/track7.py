# -*- coding: utf-8 -*-
import logging
from typing import Dict, Any, Optional
from strategy.common import TradingDateResetHelper, AtomicBudgetManager

logger = logging.getLogger(__name__)

class Track7:
    """
    [Track7] Volatility Arbitrage / Skew Trading & Weekly Tail Insurance
    - 자본 배분: 매주 상장 후 조건 만족 시 +0.5% 동적 부여
    - 역할:
      1. 매주 위클리 옵션 개장 첫날 상하방 극외가 양매수 구축.
      2. Call/Put IV Skew 괴리 탐지 및 변동성 차익거래(Skew Trading) 실행.
      3. 독립 예산 풀(insurance_budget_pool) 및 AtomicBudgetManager 범위 내에서 진입.
      4. IV Skew 왜곡 심화 시 손절 가드 및 만기금요일 15:15 강제 청산.
    """
    def __init__(self, config: Dict[str, Any]):
        self.params = config.get("strategies", {}).get("strategy_7", {}).get("params", {})
        # 등가격 ATM 대비 옵션 격리 거리 (행사가 격리 포인트)
        self.strike_offset = self.params.get("strike_offset", 15.0)
        # 매수 계약수
        self.insurance_qty = self.params.get("insurance_qty", 1)
        
        self.skew_active: bool = False
        self.date_reset_helper = TradingDateResetHelper()
        self.budget_manager = AtomicBudgetManager(initial_budget=0.0)
        self.reset_state()
        logger.info("Volatility Arbitrage & Weekly Insurance Strategy (Track7) Initialized.")

    def reset_state(self) -> None:
        self.insurance_state: Dict[str, Any] = {
            "is_active": False,
            "bought_date": None,
            "long_put_strike": 0.0,
            "long_call_strike": 0.0,
            "premium_spent": 0.0,
        }
        self.skew_active = False

    async def evaluate_insurance_buy_async(self, 
                                          current_price: float, 
                                          budget: float, 
                                          date_str: str, 
                                          is_new_week_start: bool,
                                          active_vol: float = 1.0) -> Dict[str, Any]:
        """
        [비동기 원자적 예산 차감 반영 위클리 보험 진입 판단]
        """
        if self.date_reset_helper.check_and_update(date_str):
            self.reset_state()

        if self.insurance_state["is_active"]:
            return {"status": "ALREADY_ACTIVE", "signals": []}

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

        logger.warning("[WEEKLY INSURANCE TRIGGER] 위클리 옵션 상장 첫날 감지! 주간 헤지 양매수 구축.")
        signals.append({
            "action": "BUY_WEEKLY_INSURANCE",
            "reason": "New trading week started. Setting up weekly long strangle protection.",
            "put_strike": long_put,
            "call_strike": long_call,
            "qty": self.insurance_qty,
            "cost": estimated_cost
        })
        return {"status": "TRIGGERED", "signals": signals}

    def evaluate_insurance_buy(self, 
                               current_price: float, 
                               budget: float, 
                               date_str: str, 
                               is_new_week_start: bool,
                               active_vol: float = 1.0) -> Dict[str, Any]:
        """
        [동기 방식 호환 주간 상장 첫날 위클리 보험 진입 판단]
        """
        if self.date_reset_helper.check_and_update(date_str):
            self.reset_state()

        if self.insurance_state["is_active"]:
            return {"status": "ALREADY_ACTIVE", "signals": []}

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

        logger.warning("[WEEKLY INSURANCE TRIGGER] 위클리 옵션 상장 첫날 감지! 주간 헤지 양매수 포지션 구축.")
        signals.append({
            "action": "BUY_WEEKLY_INSURANCE",
            "reason": "New trading week started. Setting up weekly long strangle protection.",
            "put_strike": long_put,
            "call_strike": long_call,
            "qty": self.insurance_qty,
            "cost": estimated_cost
        })
        return {"status": "TRIGGERED", "signals": signals}

    def evaluate_skew_arbitrage(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        [IV Skew 괴리 탐지 차익거래 및 왜곡 손절 로직]
        - Call IV vs Put IV Skew 괴리 탐지 시 Skew Arbitrage 시그널 발행.
        - Track 7 전용 손익/수수료 스코프 키 우선 참조.
        - Skew 왜곡 심화(|skew| > 8.0) 시 손절/헷지 전환 시그널 생성.
        """
        date_str = market_data.get("date_str", "UNKNOWN")
        if self.date_reset_helper.check_and_update(date_str):
            self.reset_state()

        # [스코프 격리] Track 7 전용 키 우선 참조
        raw_pnl = market_data.get("track7_current_pnl") if market_data.get("track7_current_pnl") is not None else market_data.get("current_pnl", 0.0)
        raw_fees = market_data.get("track7_total_fees") if market_data.get("track7_total_fees") is not None else market_data.get("total_fees", 0.0)
        current_pnl: float = float(raw_pnl or 0.0)
        total_fees: float = float(raw_fees or 0.0)

        call_iv = float(market_data.get("call_iv", 0.0))
        put_iv = float(market_data.get("put_iv", 0.0))
        skew = put_iv - call_iv

        signals = []

        # 1. Skew 괴리 이탈 시 차익거래 진입 (|skew| >= 3.0)
        if not self.skew_active:
            if abs(skew) >= 3.0:
                self.skew_active = True
                action_type = "LONG_PUT_SHORT_CALL" if skew > 0 else "LONG_CALL_SHORT_PUT"
                signals.append({
                    "action": "ENTER_SKEW_ARB",
                    "type": action_type,
                    "skew": skew,
                    "reason": f"IV Skew divergence ({skew:.2f}) detected. Executing Skew Arbitrage.",
                    "qty": 1
                })
                return {"status": "SKEW_ENTERED", "signals": signals}

        # 2. 보유 중일 때 손절 및 회귀 청산
        else:
            # Skew 왜곡 심화 (|skew| > 8.0) 시 손절
            if abs(skew) > 8.0:
                self.skew_active = False
                signals.append({
                    "action": "CLOSE_SKEW_ARB",
                    "skew": skew,
                    "reason": f"IV Skew extreme distortion ({skew:.2f} > 8.0). Triggering Stop Loss.",
                    "qty": 1
                })
                return {"status": "SKEW_STOP_LOSS", "signals": signals}

            # Skew 정상 회귀 (|skew| <= 0.5) 또는 수수료 커버 시 청산
            is_fee_cover_exit = (total_fees > 0 and current_pnl >= total_fees * 1.2)
            if abs(skew) <= 0.5 or is_fee_cover_exit:
                self.skew_active = False
                reason_str = f"IV Skew returned to normal ({skew:.2f})." if not is_fee_cover_exit else f"Fee cover profit lock triggered (PnL: KRW {current_pnl:,.0f} >= 1.2x Fees)."
                signals.append({
                    "action": "CLOSE_SKEW_ARB",
                    "skew": skew,
                    "reason": reason_str,
                    "qty": 1
                })
                return {"status": "SKEW_CLOSED", "signals": signals}

        return {"status": "HOLD", "signals": []}

    def evaluate_expiry_cutoff(self, time_str: str, is_week_end: bool, date_str: str = "UNKNOWN") -> Dict[str, Any]:
        """
        [만기 주간 장 마감 또는 오후 3시 15분 강제 청산(Flat) 판단]
        """
        if self.date_reset_helper.check_and_update(date_str):
            self.reset_state()

        if not self.insurance_state["is_active"]:
            return {"status": "INACTIVE", "signals": []}

        if is_week_end and time_str >= "15:15:00":
            signals = []
            logger.critical("[WEEKLY INSURANCE CUTOFF] 15:15 주간 장마감 강제 청산 발동! 위클리 보험 포지션 전량 청산.")
            signals.append({
                "action": "CLOSE_WEEKLY_INSURANCE",
                "reason": "Weekly expiry 15:15 Time-based mandatory flat rule.",
                "put_strike": self.insurance_state["long_put_strike"],
                "call_strike": self.insurance_state["long_call_strike"],
                "qty": self.insurance_qty
            })
            self.reset_state()
            return {"status": "CUTOFF_TRIGGERED", "signals": signals}

        return {"status": "HOLD", "signals": []}

    def evaluate_take_profit(self, current_price: float) -> Dict[str, Any]:
        """
        [동적 분할 익절 (Dynamic Take-Profit) 평가]
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

        if total_intrinsic >= spent * 2.5:
            signals = []
            logger.warning("[WEEKLY INSURANCE TAKE-PROFIT] 위클리 옵션 평가이익 폭발 감지! 이익 수취 청산 집행!")
            signals.append({
                "action": "TAKE_PROFIT_WEEKLY_INSURANCE",
                "reason": f"Weekly insurance dynamic profit realization (+{((total_intrinsic/max(1.0, spent))-1)*100:.0f}% profit).",
                "realized_amount": total_intrinsic,
                "put_strike": put_k,
                "call_strike": call_k,
                "qty": qty
            })
            self.reset_state()
            return {"status": "PROFIT_TAKEN", "signals": signals, "realized": total_intrinsic}

        return {"status": "HOLD", "signals": []}
