import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class Track6:
    """
    [Track6] 데일리 테일 보험 봇 (Track 6 Daily 0DTE)
    - 자본 배분: 매일 변동성 조건 만족 시 +0.1% 동적 부여
    - 역할:
      1. 내재변동성(active_vol)이 기준치 대비 1.3배 이상 폭발할 때 극외가격 양매수(0DTE 롱 스트랭글)를 매입.
      2. 독립 예산 풀(insurance_budget_pool) 범위 내에서만 매수하여 원본 자산을 지킴.
      3. 만기일 오후 3시 15분이 되면 잔존 가치 여부와 관계없이 전량 강제 청산(Flat)하여 위험을 원천 차단.
    """
    def __init__(self, config: Dict[str, Any]):
        self.params = config.get("strategies", {}).get("strategy_6", {}).get("params", {})
        # 변동성 경보 임계 배율 (1.3배)
        self.vol_trigger_multiplier = self.params.get("vol_trigger_multiplier", 1.3)
        # 등가격 ATM 대비 옵션 격리 거리 (행사가 격리 포인트)
        self.strike_offset = self.params.get("strike_offset", 12.5)
        # 매수할 1방향당 계약수
        self.insurance_qty = self.params.get("insurance_qty", 1)
        
        self.reset_state()
        logger.info("Daily Tail Insurance Bot (Track6) Initialized.")

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
                               active_vol: float, 
                               base_vol: float, 
                               budget: float, 
                               date_str: str) -> Dict[str, Any]:
        """
        [일간 변동성 폭발 감지 및 예산 한도 내 데일리 보험 양매수 진입 판단]
        """
        if self.insurance_state["is_active"]:
            return {"status": "ALREADY_ACTIVE", "signals": []}

        # 1. 예산 확인 (최소 1계약 양매수 프리미엄 비용인 약 1.0pt = 25만 원 수준 확보 필수)
        # 극외가 옵션 1세트(콜/풋 각각 0.50pt라 가정하면 총 1.0pt) = 250,000원
        estimated_cost = 1.0 * 250000.0 * self.insurance_qty
        if budget < estimated_cost:
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

            logger.warning("🚨 [DAILY INSURANCE TRIGGER] VKOSPI 변동성 경보 감지! 당일 만기 극외가 양매수(0DTE) 개시.")
            signals.append({
                "action": "BUY_DAILY_INSURANCE",
                "reason": f"Volatility spike ({active_vol:.2f} >= {base_vol*self.vol_trigger_multiplier:.2f}) detected. Buying 0DTE protection.",
                "put_strike": long_put,
                "call_strike": long_call,
                "qty": self.insurance_qty,
                "cost": estimated_cost
            })
            return {"status": "TRIGGERED", "signals": signals}

        return {"status": "NO_TRIGGER", "signals": []}

    def evaluate_expiry_cutoff(self, time_str: str) -> Dict[str, Any]:
        """
        [만기 오후 3시 15분 강제 청산(Flat) 판단]
        """
        if not self.insurance_state["is_active"]:
            return {"status": "INACTIVE", "signals": []}

        # 15:15:00 이후 강제 청산
        if time_str >= "15:15:00":
            signals = []
            logger.critical("🔥 [DAILY INSURANCE CUTOFF] 15:15 만기 직전 강제 청산 철칙 발동! 데일리 보험 포지션 전량 청산.")
            signals.append({
                "action": "CLOSE_DAILY_INSURANCE",
                "reason": "Expiry 15:15 Time-based mandatory flat rule.",
                "put_strike": self.insurance_state["long_put_strike"],
                "call_strike": self.insurance_state["long_call_strike"],
                "qty": self.insurance_qty
            })
            self.reset_state()
            return {"status": "CUTOFF_TRIGGERED", "signals": signals}

        return {"status": "HOLD", "signals": []}
