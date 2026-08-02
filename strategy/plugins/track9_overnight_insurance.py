import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class OvernightInsuranceBot:
    """
    [전략 9] 오버나잇 전용 보험 봇 (Track 9 Overnight Insurance)
    - 역할:
      1. 매 영업일 오후 3시 15분, Track 1 (Defense)의 활성 가두리 매도 수량 파악.
      2. 활성 매도 물량의 50%에 해당하는 타겟 수량만큼 오버나잇용 극외가(OTM) 콜/풋 옵션 양매수(Long Strangle).
      3. 포지션 보유 시 다음날 발생할 수 있는 갭 상승/하락 등 오버나잇 시장 충격 리스크 헷지.
      4. Track 1의 매도 수량에 전적으로 연동되어(Symbiotic) 잉여 수량이 발생하면 부분 축소함.
    """
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}
        # 등가격 대비 오버나잇 보험의 이격도 (기본 상하방 15.0pt)
        self.strike_offset = self.config.get("strategies", {}).get("strategy_9", {}).get("params", {}).get("strike_offset", 15.0)
        self.premium_cost = 0.15 # 0.15pt 수준의 저렴한 프리미엄 가정
        
        logger.info("Track 9 Overnight Insurance Strategy (Symbiotic with Track 1) initialized.")

    def evaluate_insurance(self, 
                           current_price: float, 
                           active_sell_qty: int, 
                           current_ins_qty: int) -> Dict[str, Any]:
        """
        Track 1의 활성 가두리 수량에 연동하여 타겟 보험 수량을 맞춤.
        """
        # 1. 타겟 보험 수량 산출 (매도 물량의 50%. 매도 물량이 0보다 크면 최소 1계약, 0이면 0계약)
        target_insurance_qty = max(1, int(active_sell_qty * 0.5)) if active_sell_qty > 0 else 0
        
        if target_insurance_qty != current_ins_qty:
            if target_insurance_qty > current_ins_qty:
                # [추가 매수] 부족분만큼 신규 매입
                diff_qty = target_insurance_qty - current_ins_qty
                insurance_put_strike = round((current_price - self.strike_offset) / 2.5) * 2.5
                insurance_call_strike = round((current_price + self.strike_offset) / 2.5) * 2.5
                
                logger.info(
                    "🛡️ [Track 1 / Overnight] OTM 보험 부족분 추가 가입 (+%d계약). Target: %d (가두리 매도 수량: %d 기준)",
                    diff_qty, target_insurance_qty, active_sell_qty
                )
                
                return {
                    "status": "ADD",
                    "signals": [
                        {
                            "action": "ADD_INSURANCE",
                            "diff_qty": diff_qty,
                            "put_strike": float(insurance_put_strike),
                            "call_strike": float(insurance_call_strike),
                            "premium": float(self.premium_cost),
                            "target_qty": target_insurance_qty
                        }
                    ]
                }
            else:
                # [부분 축소] 잉여 수량 차감
                diff_qty = current_ins_qty - target_insurance_qty
                logger.info(
                    "🛡️ [Track 1 / Overnight] OTM 보험 잉여분 축소 튜닝 (-%d계약). Target: %d (가두리 매도 수량: %d 기준)",
                    diff_qty, target_insurance_qty, active_sell_qty
                )
                
                return {
                    "status": "REDUCE",
                    "signals": [
                        {
                            "action": "REDUCE_INSURANCE",
                            "diff_qty": diff_qty,
                            "target_qty": target_insurance_qty
                        }
                    ]
                }
        else:
            # [유지] 변동 없음
            if target_insurance_qty > 0:
                logger.info(
                    "🛡️ [Track 1 / Overnight] 가두리 매도(%d)와 현재 보험 수량(%d)의 균형 유지. 추가 지출 없이 홀딩.",
                    active_sell_qty, current_ins_qty
                )
            return {
                "status": "HOLD",
                "signals": [
                    {
                        "action": "HOLD_INSURANCE",
                        "target_qty": target_insurance_qty
                    }
                ]
            }
