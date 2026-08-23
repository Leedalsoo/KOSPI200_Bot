# -*- coding: utf-8 -*-
import logging
from typing import Dict, Any, Optional
from option_program.strategy.common import TradingDateResetHelper, AtomicBudgetManager, ExecutionCostCalculator, WallClockTimer, DynamicProfitRebuildEvaluator
from option_program.strategy.strategy_contract import StrategyContract



logger = logging.getLogger(__name__)

class Track8(StrategyContract):
    """
    [Track8] Macro Regime Protection & Monthly Wide Strangle
    - 자본 배분: 5% (월물 초입 지정가 분할 큐 및 D-4 다이내믹 조건부 홀딩 모듈)
    - 주요 메커니즘:
      1. 월물 초입(DTE >= 15.0) 시장가 슬리피지 방지를 위해 지정가 분할 큐(Limit Order Tranche Queue) 매수 진입.
      2. 15:15 장 마감 미체결 주문 일괄 취소 및 익일 아침 시초가 갭 기반 동적 재배치(DYNAMIC_REPRICE).
      3. 만기 D-4~D-0 구간 무조건 일괄 청산 대신, Moneyness(±3% 이내) 및 IV 팽창 여부를 다이내믹 재평가.
      4. 조건 경계선 부근 핑퐁 휩쏘 매매를 방지하는 시간 가중 히스테리시스 필터(Hysteresis Filter) 적용.
    """
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}
        self.min_budget_requirement = 200000.0  # 최소 20만 원 적립 한도
        self.date_reset_helper = TradingDateResetHelper()
        self.budget_manager = AtomicBudgetManager(initial_budget=0.0)
        self.hysteresis_hold_counter: int = 0  # 핑퐁 방지용 시간 가중 히스테리시스 필터 카운터
        
        # Dynamic Profit Take & Rebuild Evaluator
        self.rebuild_evaluator = DynamicProfitRebuildEvaluator()
        self.profit_target = float(self.config.get("profit_target", 300000.0))

        self.reset_state()
        logger.info("Macro Regime Protection & Monthly Wide Strangle Strategy (Track8) Initialized.")


    def reset_state(self) -> None:
        self.strangle_state = {
            "is_active": False,
            "premium_spent": 0.0,
            "call_strike": 0.0,
            "put_strike": 0.0,
            "qty_call": 0,
            "qty_put": 0,
            "entry_date": "",
            "high_watermark_intrinsic": 0.0,
            "trailing_stop_active": False,
        }
        self.hysteresis_hold_counter = 0

    async def evaluate_entry_async(self, 
                                 dte: float, 
                                 budget: float, 
                                 current_price: float, 
                                 current_regime: str,
                                 date_str: str) -> Dict[str, Any]:
        """
        [비동기 원자적 예산 차감 반영 월물 초입 지정가 분할 큐 진입 평가]
        """
        if self.date_reset_helper.check_and_update(date_str):
            self.reset_state()

        if self.strangle_state["is_active"]:
            return {"status": "HOLDING", "signals": []}

        if dte >= 15.0 and budget >= self.min_budget_requirement:
            skew_ratio = 2.0 if current_regime == "HIGH_VOL" else 1.5
            call_strike = round((current_price + 15.0) / 2.5) * 2.5
            put_strike = round((current_price - 15.0) / 2.5) * 2.5
            
            unit_cost = ((1.20) + (skew_ratio * 1.50)) * 250000.0
            base_qty = max(1, int(budget / max(1.0, unit_cost)))
            qty_call = base_qty
            qty_put = int(base_qty * skew_ratio)
            estimated_cost = ((qty_call * 1.20) + (qty_put * 1.50)) * 250000.0
            
            self.budget_manager.set_budget(budget)
            success, _ = await self.budget_manager.try_deduct(estimated_cost)
            if not success:
                return {"status": "NO_BUDGET", "signals": []}

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
                "[MONTHLY STRANGLE BUY] 월간 지정가 분할 큐 양매수 진입! (예산지출: KRW %s / 콜: %d계약, Strike: %.2f / 풋: %d계약, Strike: %.2f)",
                f"{estimated_cost:,.0f}", qty_call, call_strike, qty_put, put_strike
            )
            
            return {
                "status": "TRIGGERED",
                "signals": [
                    {
                        "action": "BUY_LIMIT_TRANCHE",
                        "cost": estimated_cost,
                        "qty_call": qty_call,
                        "qty_put": qty_put,
                        "call_strike": call_strike,
                        "put_strike": put_strike,
                        "pricing_mode": "MID_PRICE_OFFSET",
                        "limit_offset_ticks": 1,
                        "fallback_market_timeout_sec": 5.0,
                        "qty": 1,
                        "reason": f"DTE {dte:.1f} 월물 초입 지정가 분할 큐 진입 via Mid-Price Adapter (비대칭 스큐 {skew_ratio}x)"
                    }
                ]
            }
                
        return {"status": "STANDBY", "signals": []}

    def evaluate_entry(self, 
                       dte: float, 
                       budget: float, 
                       current_price: float, 
                       current_regime: str,
                       date_str: str) -> Dict[str, Any]:
        """
        [동기 방식 호환 월물 초입 지정가 분할 큐 진입 평가]
        """
        if self.date_reset_helper.check_and_update(date_str):
            self.reset_state()

        if self.strangle_state["is_active"]:
            return {"status": "HOLDING", "signals": []}

        if dte >= 15.0 and budget >= self.min_budget_requirement:
            skew_ratio = 2.0 if current_regime == "HIGH_VOL" else 1.5
            call_strike = round((current_price + 15.0) / 2.5) * 2.5
            put_strike = round((current_price - 15.0) / 2.5) * 2.5
            
            unit_cost = ((1.20) + (skew_ratio * 1.50)) * 250000.0
            base_qty = max(1, int(budget / max(1.0, unit_cost)))
            qty_call = base_qty
            qty_put = int(base_qty * skew_ratio)
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
                    "[MONTHLY STRANGLE BUY] 월간 지정가 분할 큐 양매수 진입! (예산지출: KRW %s / 콜: %d계약 / 풋: %d계약)",
                    f"{estimated_cost:,.0f}", qty_call, qty_put
                )
                
                return {
                    "status": "TRIGGERED",
                    "signals": [
                        {
                            "action": "BUY_LIMIT_TRANCHE",
                            "cost": estimated_cost,
                            "qty_call": qty_call,
                            "qty_put": qty_put,
                            "call_strike": call_strike,
                            "put_strike": put_strike,
                            "pricing_mode": "MID_PRICE_OFFSET",
                            "limit_offset_ticks": 1,
                            "fallback_market_timeout_sec": 5.0,
                            "qty": 1,
                            "reason": f"DTE {dte:.1f} 월물 초입 지정가 분할 큐 진입 via Mid-Price Adapter (비대칭 스큐 {skew_ratio}x)"
                        }
                    ]
                }
                
        return {"status": "STANDBY", "signals": []}

    def evaluate_take_profit(self, current_price: float, active_vol: float = 1.0) -> Dict[str, Any]:
        """
        [2단계 하이브리드 익절: VKOSPI 최소 이익선 돌파 -> High Watermark 트레일링 스탑]
        """
        if not self.strangle_state["is_active"]:
            return {"status": "INACTIVE", "signals": []}

        put_k = self.strangle_state["put_strike"]
        call_k = self.strangle_state["call_strike"]
        qty = max(self.strangle_state.get("qty_call", 1), self.strangle_state.get("qty_put", 1))

        put_intrinsic = max(0.0, put_k - current_price) * 250000.0 * qty
        call_intrinsic = max(0.0, current_price - call_k) * 250000.0 * qty
        total_intrinsic = put_intrinsic + call_intrinsic
        spent = self.strangle_state.get("premium_spent", 500000.0)

        # 1단계: VKOSPI 변동성 연동 최소 이익선 산정 (기본 1.8배)
        min_multiplier = 1.8 if active_vol < 1.3 else 2.5

        # 최소 이익선 돌파 시 트레일링 스탑 모드 가동
        if total_intrinsic >= spent * min_multiplier:
            self.strangle_state["trailing_stop_active"] = True

        # 2단계: 트레일링 스탑 가동 중 최고점 대비 3단계 동적 스케일링 반락선 지정가 예약 큐 실시간 선제 배치
        if self.strangle_state["trailing_stop_active"]:
            prev_high = self.strangle_state.get("high_watermark_intrinsic", 0.0)
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
                    "reason": f"Monthly High Watermark (KRW {current_high:,.0f}) 대비 {step_name} 반락. 트레일링 스탑 지정가 익절 완료.",
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
                self.strangle_state["high_watermark_intrinsic"] = current_high
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

    def evaluate_macro_regime_protection(self, market_data: Dict[str, Any], current_regime: str) -> Dict[str, Any]:
        """
        [매크로 레짐 변화 감지 & 포트폴리오 리스크 스케일링]
        """
        date_str = market_data.get("date_str", "UNKNOWN")
        if self.date_reset_helper.check_and_update(date_str):
            self.reset_state()

        raw_pnl = market_data.get("track8_current_pnl") if market_data.get("track8_current_pnl") is not None else market_data.get("current_pnl", 0.0)
        raw_fees = market_data.get("track8_total_fees") if market_data.get("track8_total_fees") is not None else market_data.get("total_fees", 0.0)
        current_pnl: float = float(raw_pnl or 0.0)
        total_fees: float = float(raw_fees or 0.0)

        signals = []
        if current_regime in ["HIGH_VOL", "CIRCUIT_BREAKER", "CRASH"]:
            logger.warning("[MACRO REGIME RISK] 고변동성/파국 위험 레짐(%s) 감지. 포트폴리오 헷지 비율 강화.", current_regime)
            signals.append({
                "action": "MACRO_HEDGE_SCALE_UP",
                "regime": current_regime,
                "hedge_ratio_multiplier": 1.5,
                "qty": 1,
                "reason": f"Macro Risk Regime ({current_regime}) detected. Scaling up portfolio hedges."
            })
            return {"status": "RISK_SCALE_UP", "signals": signals}

        return {"status": "HOLD", "signals": []}

    def evaluate_expiry_cutoff(self, 
                              dte: float, 
                              current_price: float = 0.0, 
                              active_vol: float = 1.0, 
                              time_str: str = "09:00:00", 
                              date_str: str = "UNKNOWN") -> Dict[str, Any]:
        """
        [만기 D-4~D-0 다이내믹 3중 루프 & 시간 가중 히스테리시스 조건부 홀딩]
        """
        if self.date_reset_helper.check_and_update(date_str):
            self.reset_state()

        if not self.strangle_state["is_active"]:
            return {"status": "STANDBY", "signals": []}

        # 15:15 장 마감 미체결 지정가 주문 일괄 취소 시그널
        if "15:15" <= time_str < "15:20":
            return {
                "status": "CANCEL_PENDING",
                "signals": [{
                    "action": "CANCEL_PENDING_TRANCHES",
                    "reason": "15:15 장 마감에 따른 미체결 지정가 분할 큐 일괄 취소 (오버나잇 갭 방지)"
                }]
            }

        # 만기 D-4~D-0 다이내믹 조건부 홀딩 재평가
        if dte <= 4.0:
            call_k = self.strangle_state["call_strike"]
            put_k = self.strangle_state["put_strike"]
            
            # Moneyness(±3% 이내 접근) 및 IV 팽창 여부 체크
            is_near_call = (call_k > 0 and abs(current_price - call_k) / max(1.0, call_k) <= 0.03)
            is_near_put = (put_k > 0 and abs(current_price - put_k) / max(1.0, put_k) <= 0.03)
            is_iv_expanded = (active_vol >= 1.5)
            
            # 조건 만족 시 만기까지 롱 공격 보존을 위해 홀딩 유예
            if is_near_call or is_near_put or is_iv_expanded:
                self.hysteresis_hold_counter += 1
                logger.info(
                    "🎯 [DYNAMIC HOLD PRESERVED] 만기 D-4 구간 Moneyness/IV 충족 (카운트: %d) -> 홀딩 유예 집행!",
                    self.hysteresis_hold_counter
                )
                return {
                    "status": "DYNAMIC_HOLD_PRESERVED",
                    "signals": [{
                        "action": "HOLD_LONG_ATTACK",
                        "reason": f"DTE {dte:.1f} Moneyness(±3%) or IV({active_vol:.2f}) expansion. Preserving Long Attack."
                    }]
                }

            # 시간 가중 히스테리시스 필터: 핑퐁 방지를 위해 카운터가 남아있는 경우 컷오프 유예
            if self.hysteresis_hold_counter > 0:
                self.hysteresis_hold_counter -= 1
                return {
                    "status": "HYSTERESIS_FILTER_ACTIVE",
                    "signals": [{
                        "action": "HOLD_HYSTERESIS",
                        "reason": "시간 가중 히스테리시스 필터 작동 (핑퐁 방지 유예)"
                    }]
                }

            # 지수가 중앙 박스권에 갇혀 있고 OTM 휴지조각 직전일 때만 D-4 컷오프 실행
            logger.warning("[MONTHLY STRANGLE CUTOFF] DTE %.2f일 OTM 잔존 세타 소모 차단 컷오프 집행", dte)
            spent = self.strangle_state["premium_spent"]
            qty_call = self.strangle_state["qty_call"]
            qty_put = self.strangle_state["qty_put"]
            self.reset_state()
            
            return {
                "status": "CUTOFF_TRIGGERED",
                "signals": [
                    {
                        "action": "FLAT_STRANGLE",
                        "qty_call": qty_call,
                        "qty_put": qty_put,
                        "premium_spent": spent,
                        "qty": 1,
                        "reason": f"만기 D-4일({dte:.1f}) OTM 잔존 프리미엄 회수 컷오프"
                    }
                ]
            }
            
        return {"status": "HOLDING", "signals": []}

    def evaluate_dynamic_profit_rebuild(
        self,
        current_price: float,
        unrealized_pnl: float,
        qty: int = 1,
        margin_ratio: float = 0.0,
        risk_guard_active: bool = False,
        tick_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        [Dynamic Profit-Take & Rebuild] Track 8 Macro Wide Strangle 이익 실현 및 헷지 공백 없는 신규 Strangle 구축
        - Expected Net PnL >= profit_target 만족 시 기존 Wide Strangle Profit-Take 청산 후 재구축.
        - Risk Guard 발동 또는 margin_ratio 과다 시 신규 Rebuild 차단.
        - 헷지 공백 방지 순서: 1) 기존 포지션 DYNAMIC_PROFIT_TAKE 신호발행, 2) 신규 Wide Strangle 가두리 DYNAMIC_REBUILD_FENCE 산출.
        """
        if risk_guard_active or margin_ratio > 0.85:
            logger.warning("🚨 [Track 8 Rebuild Blocked] Risk Guard 발동 또는 Margin Ratio (%.2f) 초과로 Rebuild 차단.", margin_ratio)
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
        old_call = self.strangle_state.get("call_strike", current_price + 15.0)
        old_put = self.strangle_state.get("put_strike", current_price - 15.0)

        # 1. OLD HEDGE Profit Take & Exit
        signals.append({
            "action": "DYNAMIC_PROFIT_TAKE",
            "call_strike": old_call,
            "put_strike": old_put,
            "qty": qty,
            "net_pnl": net_pnl,
            "reason": f"Track 8 Net PnL (KRW {net_pnl:,.0f}) 목표 달성. Macro Strangle Profit Take!"
        })

        # 2. NEW HEDGE Rebuild (중심가격 기준 신규 Strangle 산출)
        call_strike_new, put_strike_new = self.rebuild_evaluator.calculate_rebuild_strikes(
            current_price=current_price,
            offset=15.0
        )

        self.strangle_state.update({
            "is_active": True,
            "call_strike": call_strike_new,
            "put_strike": put_strike_new,
            "high_watermark_intrinsic": 0.0,
            "trailing_stop_active": False
        })

        signals.append({
            "action": "DYNAMIC_REBUILD_FENCE",
            "call_strike": call_strike_new,
            "put_strike": put_strike_new,
            "qty": qty,
            "reason": "Track 8 중심가(%.2f) 기준 신규 Macro Wide Strangle 구축 (Call: %.1f, Put: %.1f)" % (
                current_price, call_strike_new, put_strike_new
            )
        })

        logger.info(
            "🔄 [Track 8 PROFIT TAKE & REBUILD] Net PnL: KRW %s | 신규 중심가: %.2f | Call: %.1f / Put: %.1f",
            f"{net_pnl:,.0f}", current_price, call_strike_new, put_strike_new
        )

        return {"status": "PROFIT_TAKEN_AND_REBUILT", "signals": signals, "net_pnl": net_pnl}

