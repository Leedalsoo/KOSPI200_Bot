import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class Track7:
    """
    [Track7] 위클리 테일 보험 봇 (Track 7 Weekly Insurance)
    - 자본 배분: 매주 상장 후 조건 만족 시 +0.5% 동적 부여
    - 역할:
      1. 매주 위클리 옵션 개장 첫날(새로운 주차 시작 시) 상하방이 넓은 극외가 양매수를 구축.
      2. 1주간 터질 수 있는 거시지표 이벤트나 추세 폭발 위험을 저비용으로 헤지.
      3. 독립 예산 풀(insurance_budget_pool) 한도 내에서만 진입하도록 연동.
    """
    def __init__(self, config: Dict[str, Any]):
        self.params = config.get("strategies", {}).get("strategy_7", {}).get("params", {})
        # 등가격 ATM 대비 옵션 격리 거리 (행사가 격리 포인트)
        self.strike_offset = self.params.get("strike_offset", 15.0)
        # 매수 계약수
        self.insurance_qty = self.params.get("insurance_qty", 1)
        
        self.reset_state()
        logger.info("Weekly Tail Insurance Bot (Track7) Initialized.")

    def reset_state(self) -> None:
        self.insurance_state: Dict[str, Any] = {
            "is_active": False,
            "bought_date": None,
            "long_put_strike": 0.0,
            "long_call_strike": 0.0,
            "premium_spent": 0.0,
        }

    def evaluate_insurance_buy(self, 
                               current_price: float, 
                               budget: float, 
                               date_str: str, 
                               is_new_week_start: bool,
                               active_vol: float = 1.0) -> Dict[str, Any]:
        """
        [주간 상장 첫날 및 예산 풀 범위 내 위클리 보험 진입 판단]
        - VKOSPI / active_vol < 1.0 (극저변동성) 구간에서는 프리미엄 유출 방지를 위해 50% 예산 투입 절감
        """
        if self.insurance_state["is_active"]:
            return {"status": "ALREADY_ACTIVE", "signals": []}

        # 1. 새로운 위클리 상품 상장 첫날(새 주차 시작일)인지 판정
        if not is_new_week_start:
            return {"status": "NOT_NEW_WEEK", "signals": []}

        # 2. VKOSPI / active_vol 극저변동성 구간 50% 절감 스케일 적용
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

        logger.warning("🚨 [WEEKLY INSURANCE TRIGGER] 위클리 옵션 상장 첫날 감지! 주간 헤지 양매수 포지션 구축.")
        signals.append({
            "action": "BUY_WEEKLY_INSURANCE",
            "reason": "New trading week started. Setting up weekly long strangle protection.",
            "put_strike": long_put,
            "call_strike": long_call,
            "qty": self.insurance_qty,
            "cost": estimated_cost
        })
        return {"status": "TRIGGERED", "signals": signals}

    def evaluate_expiry_cutoff(self, time_str: str, is_week_end: bool) -> Dict[str, Any]:
        """
        [만기 주간 장 마감 또는 오후 3시 15분 강제 청산(Flat) 판단]
        """
        if not self.insurance_state["is_active"]:
            return {"status": "INACTIVE", "signals": []}

        # 만기 금요일 장마감 직전(15:15:00) 혹은 영업일 종료 시
        if is_week_end and time_str >= "15:15:00":
            signals = []
            logger.critical("🔥 [WEEKLY INSURANCE CUTOFF] 15:15 주간 장마감 강제 청산 발동! 위클리 보험 포지션 전량 청산.")
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
        - 지수가 상/하방으로 크게 튀어 위클리 옵션의 내재가치 평가금액이
          매수 프리미엄 지출액 대비 2.5배(+150%) 이상 상회할 때 장중 익절 청산집행.
        """
        if not self.insurance_state["is_active"]:
            return {"status": "INACTIVE", "signals": []}

        put_k = self.insurance_state["long_put_strike"]
        call_k = self.insurance_state["long_call_strike"]
        qty = self.insurance_qty

        # 현재 지수 기반 내재가치 가늠 (1계약당 25만 원 곱함)
        put_intrinsic = max(0.0, put_k - current_price) * 250000.0 * qty
        call_intrinsic = max(0.0, current_price - call_k) * 250000.0 * qty
        total_intrinsic = put_intrinsic + call_intrinsic

        spent = self.insurance_state.get("premium_spent", 350000.0)

        if total_intrinsic >= spent * 2.5:  # 2.5배 이상 수익 시 장중 이익 실현
            signals = []
            logger.warning(f"🎉 [WEEKLY INSURANCE TAKE-PROFIT] 위클리 옵션 평가이익 폭발 감지! (평가금: ₩{total_intrinsic:,.0f} / 프리미엄: ₩{spent:,.0f}). 이익 수취 청산 집행!")
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

