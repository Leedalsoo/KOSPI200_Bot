# -*- coding: utf-8 -*-
import logging
from typing import Dict, Any, Optional
from strategy.common import TradingDateResetHelper, AtomicBudgetManager

logger = logging.getLogger(__name__)

class Track9:
    """
    [Track9] Event Driven / Earnings Volatility Spike & Overnight Insurance
    - 역할:
      1. 매 영업일 오후 3시 15분, Track 1의 활성 가두리 매도 수량 파악 후 오버나잇 헤지 수량 맞춤.
      2. 주요 거시지표/실적 발표 전 IV Spike 탐지 시 이벤트 전용 롱 스트랭글 진입.
      3. 이벤트 직후 Vol Crush(변동성 급락) 발생 시 즉시 익절/손절 청산.
      4. 독립 예산 풀 및 AtomicBudgetManager 동시성 원자적 관리.
    """
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}
        self.strike_offset = self.config.get("strategies", {}).get("strategy_9", {}).get("params", {}).get("strike_offset", 15.0)
        self.premium_cost = 0.15
        
        self.event_active: bool = False
        self.date_reset_helper = TradingDateResetHelper()
        self.budget_manager = AtomicBudgetManager(initial_budget=0.0)
        self.reset_state()
        logger.info("Track 9 Event Driven & Overnight Insurance Strategy initialized.")

    def reset_state(self) -> None:
        self.event_active = False

    def evaluate_insurance(self, 
                            current_price: float, 
                            active_sell_qty: int, 
                            current_ins_qty: int,
                            date_str: str = "UNKNOWN") -> Dict[str, Any]:
        """
        Track 1의 활성 가두리 수량에 연동하여 타겟 보험 수량을 맞춤.
        """
        if self.date_reset_helper.check_and_update(date_str):
            self.reset_state()

        target_insurance_qty = max(1, int(active_sell_qty * 0.5)) if active_sell_qty > 0 else 0
        
        if target_insurance_qty != current_ins_qty:
            if target_insurance_qty > current_ins_qty:
                diff_qty = target_insurance_qty - current_ins_qty
                insurance_put_strike = round((current_price - self.strike_offset) / 2.5) * 2.5
                insurance_call_strike = round((current_price + self.strike_offset) / 2.5) * 2.5
                
                logger.info(
                    "[Track 1 / Overnight] OTM 보험 부족분 추가 가입 (+%d계약). Target: %d",
                    diff_qty, target_insurance_qty
                )
                
                return {
                    "status": "ADD",
                    "signals": [
                        {
                            "action": "ADD_INSURANCE",
                            "diff_qty": diff_qty,
                            "put_strike": insurance_put_strike,
                            "call_strike": insurance_call_strike,
                            "premium": self.premium_cost,
                            "target_qty": target_insurance_qty,
                            "qty": diff_qty
                        }
                    ]
                }
            else:
                diff_qty = current_ins_qty - target_insurance_qty
                logger.info(
                    "[Track 1 / Overnight] OTM 보험 잉여분 축소 튜닝 (-%d계약). Target: %d",
                    diff_qty, target_insurance_qty
                )
                
                return {
                    "status": "REDUCE",
                    "signals": [
                        {
                            "action": "REDUCE_INSURANCE",
                            "diff_qty": diff_qty,
                            "target_qty": target_insurance_qty,
                            "qty": diff_qty
                        }
                    ]
                }
        else:
            return {
                "status": "HOLD",
                "signals": [
                    {
                        "action": "HOLD_INSURANCE",
                        "target_qty": target_insurance_qty,
                        "qty": 0
                    }
                ]
            }

    async def evaluate_event_buy_async(self, budget: float, estimated_cost: float) -> bool:
        """
        [비동기 원자적 이벤트 예산 차감]
        """
        self.budget_manager.set_budget(budget)
        success, _ = await self.budget_manager.try_deduct(estimated_cost)
        return success

    def evaluate_event_volatility_spike(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        [이벤트 전 IV Spike 진입 및 이벤트 후 Vol Crush 청산]
        """
        date_str = market_data.get("date_str", "UNKNOWN")
        if self.date_reset_helper.check_and_update(date_str):
            self.reset_state()

        # [스코프 격리] Track 9 전용 키 우선 참조
        raw_pnl = market_data.get("track9_current_pnl") if market_data.get("track9_current_pnl") is not None else market_data.get("current_pnl", 0.0)
        raw_fees = market_data.get("track9_total_fees") if market_data.get("track9_total_fees") is not None else market_data.get("total_fees", 0.0)
        current_pnl: float = float(raw_pnl or 0.0)
        total_fees: float = float(raw_fees or 0.0)

        is_event_upcoming = bool(market_data.get("is_event_upcoming", False))
        iv_spike = float(market_data.get("iv_spike", 0.0))
        iv_crush = float(market_data.get("iv_crush", 0.0))

        signals = []

        # 1. 진입 조건: 이벤트 전이거나 IV Spike 급등 (iv_spike >= 4.0)
        if not self.event_active:
            if is_event_upcoming or iv_spike >= 4.0:
                self.event_active = True
                signals.append({
                    "action": "ENTER_EVENT_STRANGLE",
                    "reason": f"Event upcoming ({is_event_upcoming}) / IV Spike ({iv_spike:.2f}). Entering Event Long Strangle.",
                    "qty": 1
                })
                return {"status": "EVENT_ENTERED", "signals": signals}

        # 2. 보유 조건: Vol Crush (iv_crush <= -3.0) 발생 또는 수수료 커버 시 청산
        else:
            is_fee_cover_exit = (total_fees > 0 and current_pnl >= total_fees * 1.2)
            if iv_crush <= -3.0 or is_fee_cover_exit:
                self.event_active = False
                reason_str = f"Event passed. Vol Crush ({iv_crush:.2f}) detected." if not is_fee_cover_exit else f"Fee cover profit lock triggered (PnL: KRW {current_pnl:,.0f} >= 1.2x Fees)."
                signals.append({
                    "action": "CLOSE_EVENT_STRANGLE",
                    "reason": reason_str,
                    "qty": 1
                })
                return {"status": "EVENT_CLOSED", "signals": signals}

        return {"status": "HOLD", "signals": []}
