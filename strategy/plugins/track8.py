# -*- coding: utf-8 -*-
import logging
from typing import Dict, Any, Optional
from strategy.common import TradingDateResetHelper, AtomicBudgetManager

logger = logging.getLogger(__name__)

class Track8:
    """
    [Track8] Macro Regime Protection & Monthly Wide Strangle
    - 자본 배분: 5% (월물 초입 롱 감마 및 거대 추세 사냥 모듈)
    - 역할:
      1. 월물 옵션 만기 초입(DTE >= 15.0)에 외가격 양매수 포지션을 구축하여 거대 추세와 롱 감마 수익 사냥.
      2. 자본 5% 범위 예산 내에서만 자금 조달 및 AtomicBudgetManager 동시성 관리.
      3. 지표상 취약한 하방 위주로 풋 수량을 더 가중하는 비대칭 스큐(Skew) 설계.
      4. 매크로 레짐(HIGH_VOL / CIRCUIT_BREAKER / CRASH) 변화 감지 시 포트폴리오 헷지 강화.
      5. 만기 D-4(DTE <= 4.0) 도달 시 일괄 청산(Flat)하고 감마 스캘핑으로 가치를 양도.
    """
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}
        self.min_budget_requirement = 200000.0  # 최소 20만 원 적립 한도
        self.date_reset_helper = TradingDateResetHelper()
        self.budget_manager = AtomicBudgetManager(initial_budget=0.0)
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
            "entry_date": ""
        }

    async def evaluate_entry_async(self, 
                                 dte: float, 
                                 budget: float, 
                                 current_price: float, 
                                 current_regime: str,
                                 date_str: str) -> Dict[str, Any]:
        """
        [비동기 원자적 예산 차감 반영 월물 초입 진입 평가]
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
                "[MONTHLY STRANGLE BUY] 월간 비대칭 풋편향 양매수 진입! (예산지출: KRW %s / 콜: %d계약, Strike: %.2f / 풋: %d계약, Strike: %.2f)",
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
                        "qty": 1,
                        "reason": f"DTE {dte:.1f} 월물 초입 진입 (비대칭 스큐 {skew_ratio}x)"
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
        [동기 방식 호환 월물 초입 진입 평가]
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
                    "[MONTHLY STRANGLE BUY] 월간 비대칭 풋편향 양매수 진입! (예산지출: KRW %s / 콜: %d계약 / 풋: %d계약)",
                    f"{estimated_cost:,.0f}", qty_call, qty_put
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
                            "qty": 1,
                            "reason": f"DTE {dte:.1f} 월물 초입 진입 (비대칭 스큐 {skew_ratio}x)"
                        }
                    ]
                }
                
        return {"status": "STANDBY", "signals": []}


    def evaluate_macro_regime_protection(self, market_data: Dict[str, Any], current_regime: str) -> Dict[str, Any]:
        """
        [매크로 레짐 변화 감지 & 포트폴리오 리스크 스케일링]
        - 고변동성/파국 위험 레짐(HIGH_VOL, CIRCUIT_BREAKER, CRASH) 감지 시 포트폴리오 헷지 스케일 업 시그널 발행.
        - Track 8 전용 손익/수수료 스코프 키 우선 참조.
        """
        date_str = market_data.get("date_str", "UNKNOWN")
        if self.date_reset_helper.check_and_update(date_str):
            self.reset_state()

        # [스코프 격리] Track 8 전용 키 우선 참조
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

        # 수수료 방어 조기 익절 조건
        if self.strangle_state["is_active"] and total_fees > 0 and current_pnl >= total_fees * 1.2:
            signals.append({
                "action": "FLAT_STRANGLE",
                "qty_call": self.strangle_state["qty_call"],
                "qty_put": self.strangle_state["qty_put"],
                "qty": 1,
                "reason": f"Fee cover profit lock triggered (PnL: KRW {current_pnl:,.0f} >= 1.2x Fees)."
            })
            self.reset_state()
            return {"status": "PROFIT_TAKEN", "signals": signals}

        return {"status": "HOLD", "signals": []}

    def evaluate_expiry_cutoff(self, dte: float, date_str: str = "UNKNOWN") -> Dict[str, Any]:
        """
        [D-4 출구 전략 집행]
        """
        if self.date_reset_helper.check_and_update(date_str):
            self.reset_state()

        if not self.strangle_state["is_active"]:
            return {"status": "STANDBY", "signals": []}
            
        if dte <= 4.0:
            logger.warning("[MONTHLY STRANGLE CUTOFF] 만기 D-4일(%.2f) 도달로 월간 양매수 포지션 강제 청산(Flat) 집행!", dte)
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
                        "reason": f"만기 D-4일({dte:.1f}) 도달 강제 회수 및 감마이양"
                    }
                ]
            }
            
        return {"status": "HOLDING", "signals": []}
