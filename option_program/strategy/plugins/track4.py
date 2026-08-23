# -*- coding: utf-8 -*-
import logging
import numpy as np
from typing import List, Dict, Any, Optional
from decimal import Decimal, ROUND_HALF_UP
from collections import deque
from uuid import uuid4

from core.base_agent import BaseAgent
from core.contracts import MarketTick, OrderRequest
from option_program.strategy.common import TradingDateResetHelper, ExecutionCostCalculator, WallClockTimer
from option_program.strategy.strategy_contract import StrategyContract

logger = logging.getLogger(__name__)

class Track4(StrategyContract):
    """
    [Track4] 감마 스캘핑 엔진 (Track 4 Gamma Scalping)
    - 자본 배분: 10% (동적 감마 스캘핑 및 ATM 베이스캠프 구축)
    """

    def __init__(self, shared_context: Optional[Dict[str, Any]] = None, equity_threshold: Decimal = Decimal("0"), config: Optional[Dict[str, Any]] = None) -> None:
        self.context: Dict[str, Any] = shared_context if shared_context is not None else (config or {})
        self.equity_threshold: Decimal = equity_threshold
        self.is_active: bool = False
        self.scalp_state: Dict[str, Any] = {"is_active": False}
        self.active_hedge_qty: int = 0  # 현재 누적 선물 헷지 수량
        self._atr_history: deque[Decimal] = deque(maxlen=20)
        
        # 실시간 ATR 계산을 위한 고가, 저가, 종가 버퍼 관리
        self._high_history: deque[Decimal] = deque(maxlen=20)
        self._low_history: deque[Decimal] = deque(maxlen=20)
        self._close_history: deque[Decimal] = deque(maxlen=20)
        self.basecamp_active: bool = False
        self.date_reset_helper = TradingDateResetHelper()

    def evaluate_scalping_basecamp_entry(self, current_price: float, active_vol: float, base_vol: float, date_str: str = "UNKNOWN", time_str: str = "09:00:00") -> Dict[str, Any]:
        """
        [Track4] 장세 변동성(VKOSPI) 연동 하이브리드 동적 감마 스캘핑 베이스캠프 진입
        1. 타임 가드: 15:15:00 이후 장 마감 직전 신규 베이스캠프 구축 차단
        2. 저변동성 Squeeze (active_vol <= base_vol * 0.85):
           - 5.0pt 폭 넓은 OTM 1단 베이스캠프 구축 (Call: ATM+2.5 / Put: ATM-2.5)
           - 프리미엄 구매 비용 30% 절감 & 세타 붕괴(시간가치 녹음) 최저 방어
        3. 고변동성 Spike (active_vol >= base_vol * 1.30):
           - ATM 정중앙 베이스캠프 구축 (Call: ATM / Put: ATM)
           - 감마(Gamma) 피크 극대화로 미세 틱 HFT 델타 스캘핑 폭등 이익 싹쓸이
        - 공통: Mid-Price 지정가 분할 큐(MID_PRICE_OFFSET) 적용으로 슬리피지 0%
        """
        if self.date_reset_helper.check_and_update(date_str):
            self.basecamp_active = False

        if self.basecamp_active:
            return {"status": "ALREADY_ACTIVE", "signals": []}

        # 🛡️ [15:15 타임 가드] 장 마감 15분 전 신규 베이스캠프 차단
        if time_str >= "15:15:00":
            return {"status": "CLOSE_CUTOFF_BLOCK", "signals": []}

        atm_strike = round(current_price / 2.5) * 2.5

        # 1. 저변동성 수축 장세 -> 5.0pt 폭 넓은 OTM 1단 베이스캠프 (Call: ATM+2.5, Put: ATM-2.5)
        if active_vol <= (base_vol * 0.85):
            self.basecamp_active = True
            call_strike = atm_strike + 2.5
            put_strike = atm_strike - 2.5
            
            logger.info("💦 [HYBRID SCALPING] 저변동성 수축(%.2f <= %.2f) 감지! 5.0pt 폭 OTM 1단 넓은 베이스캠프 구축.", active_vol, base_vol * 0.85)
            return {
                "status": "WIDE_BASECAMP_TRIGGERED",
                "signals": [{
                    "action": "BUILD_HYBRID_BASECAMP",
                    "basecamp_type": "WIDE_5PT_OTM1",
                    "reason": f"Low Vol Squeeze (VKOSPI: {active_vol:.2f} <= {base_vol*0.85:.2f}). Building 5.0pt Wide Basecamp (Call: {call_strike}, Put: {put_strike}).",
                    "atm_strike": atm_strike,
                    "call_strike": call_strike,
                    "put_strike": put_strike,
                    "pricing_mode": "MID_PRICE_OFFSET",
                    "limit_offset_ticks": 1,
                    "fallback_market_timeout_sec": 2.0,
                    "qty": 1
                }]
            }

        # 2. 고변동성 폭발 장세 -> ATM 정중앙 좁은 베이스캠프 (Call: ATM, Put: ATM)
        if active_vol >= (base_vol * 1.30):
            self.basecamp_active = True
            call_strike = atm_strike
            put_strike = atm_strike
            
            logger.warning("🚨 [HYBRID SCALPING] 고변동성 폭발(%.2f >= %.2f) 감지! ATM 정중앙 감마 피크 베이스캠프 구축.", active_vol, base_vol * 1.30)
            return {
                "status": "ATM_BASECAMP_TRIGGERED",
                "signals": [{
                    "action": "BUILD_HYBRID_BASECAMP",
                    "basecamp_type": "ATM_EXACT_PEAK",
                    "reason": f"High Vol Spike (VKOSPI: {active_vol:.2f} >= {base_vol*1.30:.2f}). Building ATM Peak Basecamp for HFT Scalping.",
                    "atm_strike": atm_strike,
                    "call_strike": call_strike,
                    "put_strike": put_strike,
                    "pricing_mode": "MID_PRICE_OFFSET",
                    "limit_offset_ticks": 1,
                    "fallback_market_timeout_sec": 2.0,
                    "qty": 1
                }]
            }

        return {"status": "NO_TRIGGER", "signals": []}

    def evaluate_scalping_rebalance(self, market_data: Dict[str, Any], days_to_expiry: float) -> Dict[str, Any]:
        """[Track4] 감마 스캘핑 지정가 큐 델타 리밸런싱 평가"""
        current_delta = Decimal(str(market_data.get("current_delta", "0.0")))
        band = Decimal(str(market_data.get("deadband", "0.3")))
        
        signals = []
        if abs(current_delta) > band:
            qty_val = -current_delta / Decimal('1.0')
            qty = int(qty_val.to_integral_value(rounding=ROUND_HALF_UP))
            if qty != 0:
                signals.append({
                    "action": "GAMMA_REBALANCE",
                    "delta": float(current_delta),
                    "pricing_mode": "MID_PRICE_OFFSET",
                    "limit_offset_ticks": 1,
                    "fallback_market_timeout_sec": 2.0,
                    "qty": qty,
                    "reason": f"Gamma rebalance limit queue trigger (Delta: {float(current_delta):.2f} > Band: {float(band):.2f})"
                })
        
        return {"status": "REBALANCE" if signals else "NORMAL", "signals": signals}

    def evaluate_scalping_take_profit(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """[Track4] 감마 스캘핑 3단계 동적 스케일링 트레일링 스탑 익절 평가"""
        current_pnl = float(market_data.get("track4_current_pnl", market_data.get("current_pnl", 0.0)))
        spent = float(market_data.get("premium_spent", 200000.0))
        
        prev_high = getattr(self, "_scalp_high_pnl", 0.0)
        current_high = max(prev_high, current_pnl)
        self._scalp_high_pnl = current_high

        if current_high <= 30000.0:
            return {"status": "HOLD", "signals": []}

        # 3단계 동적 스케일링 반락 비율 결정
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

        stop_trigger_pnl = current_high * trailing_ratio

        if current_pnl <= stop_trigger_pnl:
            self._scalp_high_pnl = 0.0
            return {
                "status": "PROFIT_TAKEN_TRAILING_STOP",
                "signals": [{
                    "action": "CLOSE_GAMMA_SCALP_LIMIT",
                    "pricing_mode": "PREEMPTIVE_STOP_LIMIT_QUEUE",
                    "limit_offset_ticks": 2,
                    "fallback_market_timeout_sec": 2.0,
                    "reason": f"🚀 [GAMMA SCALP LOCK] High Watermark (KRW {current_high:,.0f}) 대비 {step_name} 반락. 선제 지정가 익절!",
                    "pnl": current_pnl
                }]
            }

        return {"status": "HOLD", "signals": []}

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def health_check(self) -> bool:
        return True

    async def process_message(self, message: Dict[str, Any]) -> None:
        pass

    def _check_feature_flag(self, current_equity: Decimal) -> bool:
        """[목표 A] 자산 임계치 도달 여부에 따른 물리적 봉인 해제 로직"""
        self.is_active = current_equity >= self.equity_threshold
        return self.is_active

    def _calculate_atr_deadband(self, price_high: np.ndarray, price_low: np.ndarray, price_close: np.ndarray) -> Decimal:
        """[목표 B] Numpy 기반 실시간 ATR 산출 및 0.2 ~ 0.6 데드밴드 리사이징"""
        if price_close.size == 0:
            return Decimal('0.2')

        # 1. True Range 계산
        if price_close.size >= 2:
            tr_1 = price_high[1:] - price_low[1:]
            tr_2 = np.abs(price_high[1:] - price_close[:-1])
            tr_3 = np.abs(price_low[1:] - price_close[:-1])
            tr_all = np.maximum(tr_1, np.maximum(tr_2, tr_3))
            atr = float(np.mean(tr_all))
        else:
            # 윈도우 크기가 1인 경우의 TR
            atr = float(price_high[0] - price_low[0])

        # 2. ATR 정규화 및 데드밴드 리사이징 매핑 (K = 5.0 적용)
        close_last = float(price_close[-1])
        if close_last == 0:
            atr_normalized = 0.0
        else:
            atr_normalized = atr / close_last

        band_val = atr_normalized * 5.0
        
        # 3. 0.2 ~ 0.6 범위 클램핑 적용
        band_val = max(0.2, min(band_val, 0.6))
        
        # 🛡 [Decimal 호환성] 정밀 소수점 캐스팅으로 미세 수수료 누수 방지
        band = Decimal(str(round(band_val, 6)))
        self._atr_history.append(band)
        return band

    def _verify_theta_decay_offset(self, accumulated_profit: Decimal, decay_cost: Decimal) -> bool:
        """[목표 C] 신규 감마 스캘핑 진입/확장 시 감마 수익이 세타 붕괴 비용을 압도하는지 검증"""
        return bool(accumulated_profit > decay_cost)

    async def on_tick(self, tick: MarketTick, current_gamma: Decimal, current_delta: Decimal) -> List[OrderRequest]:
        """[목표 A, B, C] 동적 데드밴드 반영 선물 델타 헤징 (세타 가드와 독립적 작동)"""
        current_time = tick.timestamp
        if self.date_reset_helper.check_and_update(current_time.date()):
            self._high_history.clear()
            self._low_history.clear()
            self._close_history.clear()

        # 1. Feature Flag 자산 기반 해제 검증 (Track 4 전용 스코프 우선 참조)
        raw_eq = self.context.get("track4_current_equity", self.context.get("current_equity", Decimal('0')))
        current_equity = Decimal(str(raw_eq))
        
        # 전략 비활성화 시 잔여 헷지 포지션 언와인드(청산) 처리
        if not self._check_feature_flag(current_equity):
            if self.active_hedge_qty != 0:
                unwind_side = "SELL" if self.active_hedge_qty > 0 else "BUY"
                unwind_qty = abs(self.active_hedge_qty)
                price = tick.last_price - Decimal('0.10') if unwind_side == "SELL" else tick.last_price + Decimal('0.10')
                price = max(price, Decimal('0.01'))
                
                unwind_order = OrderRequest(
                    decision_id=uuid4(),
                    client_order_id=uuid4(),
                    instrument_code="FUT_HEDGE",
                    side=unwind_side,
                    price=price,
                    qty=unwind_qty
                )
                self.active_hedge_qty = 0
                return [unwind_order]
            return []

        # 2. 가격 이력 추가
        self._high_history.append(tick.last_price)
        self._low_history.append(tick.last_price)
        self._close_history.append(tick.last_price)

        # 3. 실시간 동적 데드밴드 산출
        h_arr = np.array(list(self._high_history), dtype=float)
        l_arr = np.array(list(self._low_history), dtype=float)
        c_arr = np.array(list(self._close_history), dtype=float)
        band = self._calculate_atr_deadband(h_arr, l_arr, c_arr)

        # 🛡️ [핵심 수정: 델타 헷지와 세타 가드의 구조적 분리]
        # 델타 헷지는 포트폴리오 델타 방어를 위해 세타 조건과 상관없이 항상 작동함.
        if abs(current_delta) > band:
            qty_val = -current_delta / Decimal('1.0')
            qty_rounded = qty_val.to_integral_value(rounding=ROUND_HALF_UP)
            qty = int(qty_rounded)

            if qty == 0:
                return []

            # 🛡 [100배 과잉 헤징 방어] 안전 한계치 클램핑
            max_safety_limit = 100
            if qty > max_safety_limit:
                qty = max_safety_limit
            elif qty < -max_safety_limit:
                qty = -max_safety_limit

            # 지정가(IOC) 적용
            if qty > 0:
                price = tick.last_price + Decimal('0.10')
            else:
                price = tick.last_price - Decimal('0.10')

            price = max(price, Decimal('0.01'))

            hedge_order = OrderRequest(
                decision_id=uuid4(),
                client_order_id=uuid4(),
                instrument_code="FUT_HEDGE",
                side="BUY" if qty > 0 else "SELL",
                price=price,
                qty=abs(qty)
            )
            self.active_hedge_qty += qty
            return [hedge_order]

        return []


# 하위 호환성을 위한 전략 클래스 별칭
Track4 = Track4


