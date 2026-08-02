import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class MonthlyWideStrangleStrategy:
    """
    [전략 8] 월간 넓은 양매수 전략 (Monthly Wide Strangle)
    - 자본 배분: 5% (월물 초입 롱 감마 및 거대 추세 사냥 모듈)
    - 역할:
      1. 월물 옵션 만기 초입(DTE >= 20.0)에 외가격 양매수 포지션을 구축하여 거대 추세와 롱 감마 수익 사냥.
      2. 자본 5% 범위 예산 내에서만 자금 조달.
      3. 지표상 취약한 하방 위주로 풋 수량을 더 가중하는 비대칭 스큐(Skew) 설계.
      4. 만기 D-3(DTE <= 3.0) 도달 시 일괄 청산(Flat)하고 감마 스캘핑(전략 4)으로 가치를 양도.
    """
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}
        self.min_budget_requirement = 200000.0  # 최소 20만 원 적립 한도 (월물 예산 풀 연동)
        self.strangle_state = {
            "is_active": False,
            "premium_spent": 0.0,
            "call_strike": 0.0,
            "put_strike": 0.0,
            "qty_call": 0,
            "qty_put": 0,
            "entry_date": ""
        }
        logger.info("Track 8 Monthly Wide Strangle Strategy initialized.")

    def evaluate_entry(self, 
                       dte: float, 
                       budget: float, 
                       current_price: float, 
                       current_regime: str,
                       date_str: str) -> Dict[str, Any]:
        """
        월물 초입 진입 평가
        """
        if self.strangle_state["is_active"]:
            return {"status": "HOLDING"}

        # 만기가 15일 이상 남았고 예산 요건(20만 원 이상)을 충족할 때
        if dte >= 15.0 and budget >= self.min_budget_requirement:

            # 풋 스큐 가중 배율: 변동성 국면(HIGH_VOL)일 때는 2.0배, 평시에는 1.5배 가중
            skew_ratio = 2.0 if current_regime == "HIGH_VOL" else 1.5
            
            # 행사가는 현재가 기준 상하방 15.0pt 떨어진 넓은 외가격 지정
            call_strike = round((current_price + 15.0) / 2.5) * 2.5
            put_strike = round((current_price - 15.0) / 2.5) * 2.5
            
            # 수량 결정: 예산 50만 원 당 콜 1계약 / 풋 1.5~2계약 매수
            base_qty = max(1, int(budget / 500000.0))
            qty_call = base_qty
            qty_put = int(base_qty * skew_ratio)
            
            # 프리미엄 예상 비용 (콜 1.20pt, 풋 1.50pt 모사)
            estimated_cost = ((qty_call * 1.20) + (qty_put * 1.50)) * 250000.0
            
            if budget >= estimated_cost:
                self.strangle_state.update({
                    "is_active": True,
                    "premium_spent": estimated_cost,
                    "call_strike": call_strike,
                    "put_strike": put_strike,
                    "qty_call": qty_call,
                    "qty_put": qty_put,
                    "entry_date": date_str
                })
                
                logger.warning(
                    "🚨 [MONTHLY STRANGLE BUY] 월간 비대칭 풋편향 양매수 진입! (예산지출: ₩%s / 콜: %d계약, Strike: %.2f / 풋: %d계약, Strike: %.2f)",
                    f"{estimated_cost:,.0f}", qty_call, call_strike, qty_put, put_strike
                )
                
                return {
                    "status": "TRIGGERED",
                    "signals": [
                        {
                            "action": "BUY_STRANGLE",
                            "cost": estimated_cost,
                            "qty_call": qty_call,
                            "qty_put": qty_put,
                            "call_strike": call_strike,
                            "put_strike": put_strike,
                            "reason": f"DTE {dte:.1f}월물 초입 진입 (비대칭 스큐 {skew_ratio}x)"
                        }
                    ]
                }
                
        return {"status": "STANDBY"}

    def evaluate_expiry_cutoff(self, dte: float) -> Dict[str, Any]:
        """
        D-3 출구 전략 집행
        """
        if not self.strangle_state["is_active"]:
            return {"status": "STANDBY"}
            
        # 만기 D-4일 도달 시 계좌 안전성 및 감마 폭발 방지를 위한 강제 청산 집행
        if dte <= 4.0:
            logger.warning("🏁 [MONTHLY STRANGLE CUTOFF] 만기 D-4일(%.2f) 도달로 월간 양매수/양매도 포지션 강제 청산(Flat) 집행!", dte)
            spent = self.strangle_state["premium_spent"]
            qty_call = self.strangle_state["qty_call"]
            qty_put = self.strangle_state["qty_put"]
            
            # 상태 리셋
            self.strangle_state = {
                "is_active": False,
                "premium_spent": 0.0,
                "call_strike": 0.0,
                "put_strike": 0.0,
                "qty_call": 0,
                "qty_put": 0,
                "entry_date": ""
            }
            
            return {
                "status": "CUTOFF_TRIGGERED",
                "signals": [
                    {
                        "action": "FLAT_STRANGLE",
                        "qty_call": qty_call,
                        "qty_put": qty_put,
                        "premium_spent": spent,
                        "reason": f"만기 D-3일({dte:.1f}) 도달 강제 회수 및 감마이양"
                    }
                ]
            }
            
        return {"status": "HOLDING"}
