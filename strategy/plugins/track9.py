# -*- coding: utf-8 -*-
import logging
from typing import Dict, Any, Optional
from strategy.common import TradingDateResetHelper, AtomicBudgetManager, ExecutionCostCalculator, WallClockTimer, DynamicProfitRebuildEvaluator
from strategy.strategy_contract import StrategyContract



logger = logging.getLogger(__name__)

class Track9(StrategyContract):
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
        
        # Dynamic Profit Take & Rebuild Evaluator
        self.rebuild_evaluator = DynamicProfitRebuildEvaluator()
        self.profit_target = float(self.config.get("profit_target", 400000.0))

        self.reset_state()
        logger.info("Track 9 Event Driven & Overnight Insurance Strategy initialized.")


    def reset_state(self) -> None:
        self.event_active = False
        self.early_profit_take_executed_today: bool = False
        self.reentry_executed_today: bool = False
        self.state: str = "OVERNIGHT_HEDGE"

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

        target_insurance_qty = max(1, int(active_sell_qty * 0.5))
        
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
                            "strategy_id": "Track9",
                            "order_purpose": "ENTRY",
                            "entry_reason": "OVERNIGHT_HEDGE",
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
                            "strategy_id": "Track9",
                            "order_purpose": "EXIT",
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
                        "strategy_id": "Track9",
                        "target_qty": target_insurance_qty,
                        "qty": 0
                    }
                ]
            }

    def evaluate_early_morning_profit_take(
        self,
        time_str: str,
        current_ins_qty: int,
        unrealized_pnl: float = 0.0,
        gap_rate: float = 0.0
    ) -> Dict[str, Any]:
        """
        [🌅 09:00~09:05 선제적 Early Profit Take 로직]
        장 개장 후 09:00~09:05 사이 오버나잇 헷지 옵션 가치의 80%(80~100%)를 선제 익절 청산하여
        Vol Crush(변동성 급락) 및 옵션 프리미엄 소멸 마찰 손실을 회피하고 이익을 즉시 락인합니다.
        """
        if self.early_profit_take_executed_today:
            return {"status": "EARLY_PROFIT_TAKEN", "signals": []}

        if "09:00:00" <= time_str <= "09:05:00" and current_ins_qty > 0:
            ratio = float(self.config.get("TRACK9_EARLY_PROFIT_TAKE_RATIO", 0.80))
            unwind_qty = max(1, int(current_ins_qty * ratio))
            self.early_profit_take_executed_today = True
            self.state = "EARLY_PROFIT_TAKEN"
            
            logger.info(
                "🌅 [09:00~09:05 EARLY PROFIT TAKE] 오버나잇 헷지 옵션 선제 %d계약(%.0f%%) 익절 청산 락인!",
                unwind_qty, ratio * 100.0
            )
            return {
                "status": "EARLY_PROFIT_TAKE",
                "signals": [
                    {
                        "action": "EARLY_PROFIT_TAKE",
                        "strategy_id": "Track9",
                        "order_purpose": "EXIT",
                        "exit_reason": "EARLY_PROFIT_TAKE",
                        "qty": unwind_qty,
                        "unwind_ratio": ratio,
                        "pricing_mode": "PREEMPTIVE_LIMIT_OR_MARKET",
                        "reason": f"🌅 [09:00~09:05 EARLY PROFIT TAKE] 오버나잇 헷지 {ratio*100:.0f}%({unwind_qty}계약) 선제 익절 락인!"
                    }
                ]
            }
        
        if time_str > "09:05:00" and not self.early_profit_take_executed_today:
            self.state = "MARKET_STABILIZATION_MONITORING"

        return {"status": "HOLD", "signals": []}

    def evaluate_reentry(
        self,
        time_str: str,
        current_price: float,
        target_qty: int,
        existing_qty: int,
        is_market_stable: bool = True
    ) -> Dict[str, Any]:
        """
        [09:30 이후 조건부 헷지 재진입 (Re-entry) 로직]
        09:05~09:30 관찰 후 09:30 이후 시장이 안정화되고 헷지 필요성이 있을 때 중복 없는 순수 부족분 재헤지.
        """
        if time_str < "09:30:00":
            return {"status": "MARKET_STABILIZATION_MONITORING", "signals": []}

        if self.reentry_executed_today:
            return {"status": "REHEDGE_ACTIVE", "signals": []}

        if is_market_stable and target_qty > existing_qty:
            new_hedge_qty = target_qty - existing_qty
            self.reentry_executed_today = True
            self.state = "REHEDGE_ACTIVE"
            
            insurance_put_strike = round((current_price - self.strike_offset) / 2.5) * 2.5
            insurance_call_strike = round((current_price + self.strike_offset) / 2.5) * 2.5

            logger.info(
                "🛡️ [09:30+ RE-ENTRY] 시장 안정화 확인 후 헷지 재구축 (+%d계약)",
                new_hedge_qty
            )
            return {
                "status": "REHEDGE_ENTRY",
                "signals": [
                    {
                        "action": "REHEDGE_ENTRY",
                        "strategy_id": "Track9",
                        "order_purpose": "ENTRY",
                        "entry_reason": "REHEDGE_ENTRY",
                        "qty": new_hedge_qty,
                        "put_strike": insurance_put_strike,
                        "call_strike": insurance_call_strike,
                        "premium": self.premium_cost,
                        "pricing_mode": "MID_PRICE_OFFSET",
                        "reason": f"🛡️ [09:30+ RE-ENTRY] 시장 안정화 확인 후 헷지 재구축 (+{new_hedge_qty}계약)"
                    }
                ]
            }

        return {"status": "HOLD", "signals": []}


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
                self.event_high_pnl = max(0.0, current_pnl)
                signals.append({
                    "action": "ENTER_EVENT_STRANGLE",
                    "reason": f"Event upcoming ({is_event_upcoming}) / IV Spike ({iv_spike:.2f}). Entering Event Long Strangle via Mid-Price Queue.",
                    "pricing_mode": "MID_PRICE_OFFSET",
                    "limit_offset_ticks": 1,
                    "fallback_market_timeout_sec": 2.0,
                    "qty": 1
                })
                return {"status": "EVENT_ENTERED", "signals": signals}

        # 2. 보유 조건: Vol Crush, 수수료 커버, 또는 3단계 동적 트레일링 스탑 청산
        else:
            if current_pnl > getattr(self, "event_high_pnl", 0.0):
                self.event_high_pnl = current_pnl

            spent = market_data.get("premium_spent", 250000.0)
            high_pnl = getattr(self, "event_high_pnl", 0.0)
            
            # 3단계 동적 반락 비율 결정
            pnl_ratio = high_pnl / max(1.0, spent)
            if pnl_ratio >= 2.0:
                trailing_ratio = 0.90
                step_name = "3단계(+100% 이상 잭팟 -10% 타이트)"
            elif pnl_ratio >= 1.3:
                trailing_ratio = 0.88
                step_name = "2단계(+30%~+100% -12% 조임)"
            else:
                trailing_ratio = 0.85
                step_name = "1단계(+30% 미만 -15% 유지)"

            stop_trigger_pnl = high_pnl * trailing_ratio

            # 최고점 대비 반락 시 지정가 스탑 락인
            if high_pnl > 50000.0 and current_pnl <= stop_trigger_pnl:
                self.event_active = False
                signals.append({
                    "action": "CLOSE_EVENT_STRANGLE",
                    "pricing_mode": "PREEMPTIVE_STOP_LIMIT_QUEUE",
                    "limit_offset_ticks": 2,
                    "reason": f"🚀 [EVENT JACKPOT LOCK] High Watermark (KRW {high_pnl:,.0f}) 대비 {step_name} 반락. 선제 지정가 익절!",
                    "qty": 1
                })
                return {"status": "EVENT_TRAILING_STOP", "signals": signals}

            if iv_crush <= -3.0:
                self.event_active = False
                reason_str = f"Event passed. Vol Crush ({iv_crush:.2f}) detected."
                signals.append({
                    "action": "CLOSE_EVENT_STRANGLE",
                    "pricing_mode": "MID_PRICE_OFFSET",
                    "limit_offset_ticks": 1,
                    "reason": reason_str,
                    "qty": 1
                })
                return {"status": "EVENT_CLOSED", "signals": signals}

        return {"status": "HOLD", "signals": []}

    def evaluate_dynamic_profit_rebuild(
        self,
        current_price: float,
        unrealized_pnl: float,
        time_str: str = "09:00:00",
        qty: int = 1,
        margin_ratio: float = 0.0,
        risk_guard_active: bool = False,
        tick_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        [Dynamic Profit-Take & Rebuild] Track 9 Overnight / Volatility Spike Strangle 이익 실현 및 헷지 재구축
        - 09:00~09:05 선제적 Early Profit Take 또는 장중 급변동 시 Net Expected PnL >= profit_target 만족 시 이익실현.
        - Risk Guard 발동 시 신규 Rebuild 차단.
        - 09:30 이후 또는 변동성 안정화 확인 시 최신 중심가격 기준 신규 Wide Strangle Hedge Rebuild.
        """
        if risk_guard_active or margin_ratio > 0.85:
            logger.warning("🚨 [Track 9 Rebuild Blocked] Risk Guard 발동 또는 Margin Ratio (%.2f) 초과로 Rebuild 차단.", margin_ratio)
            return {"status": "RISK_GUARD_BLOCKED", "signals": []}

        triggered, net_pnl = self.rebuild_evaluator.evaluate_profit_take(
            unrealized_pnl=unrealized_pnl,
            qty=qty,
            profit_target=self.profit_target,
            tick_id=tick_id
        )

        if not triggered:
            return {"status": "HOLD", "signals": [], "net_pnl": net_pnl}

        signals = []
        old_call = current_price + self.strike_offset
        old_put = current_price - self.strike_offset

        # 1. Early / Dynamic Profit Take 신호발행
        signals.append({
            "action": "DYNAMIC_PROFIT_TAKE",
            "call_strike": old_call,
            "put_strike": old_put,
            "qty": qty,
            "net_pnl": net_pnl,
            "time_str": time_str,
            "reason": f"Track 9 Net PnL (KRW {net_pnl:,.0f}) 목표 달성. Overnight Hedge Profit Take!"
        })

        # 2. 09:30 이후 또는 장중 급변동 안정화 시 신규 Wide Strangle Hedge Rebuild
        call_strike_new, put_strike_new = self.rebuild_evaluator.calculate_rebuild_strikes(
            current_price=current_price,
            offset=self.strike_offset
        )

        self.reentry_executed_today = True
        self.state = "REHEDGE_ACTIVE"

        signals.append({
            "action": "DYNAMIC_REBUILD_FENCE",
            "call_strike": call_strike_new,
            "put_strike": put_strike_new,
            "qty": qty,
            "reason": "Track 9 중심가(%.2f) 기준 신규 Wide Strangle Hedge 구축 (Call: %.1f, Put: %.1f)" % (
                current_price, call_strike_new, put_strike_new
            )
        })

        logger.info(
            "🔄 [Track 9 PROFIT TAKE & REBUILD] Net PnL: KRW %s | 시각: %s | 신규 중심가: %.2f | Call: %.1f / Put: %.1f",
            f"{net_pnl:,.0f}", time_str, current_price, call_strike_new, put_strike_new
        )

        return {"status": "PROFIT_TAKEN_AND_REBUILT", "signals": signals, "net_pnl": net_pnl}

