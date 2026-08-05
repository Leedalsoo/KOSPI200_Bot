# -*- coding: utf-8 -*-
import numpy as np
from typing import List, Dict, Any, Optional
from decimal import Decimal, ROUND_HALF_UP
from collections import deque
from uuid import uuid4

from core.base_agent import BaseAgent
from core.contracts import MarketTick, OrderRequest
from strategy.common import TradingDateResetHelper

class Track4(BaseAgent):
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
        self.date_reset_helper = TradingDateResetHelper()

    def evaluate_scalping_rebalance(self, market_data: Dict[str, Any], days_to_expiry: float) -> Dict[str, Any]:
        """[Track4] 감마 스캘핑 델타 리밸런싱 평가"""
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
                    "qty": qty,
                    "reason": f"Gamma rebalance trigger (Delta: {float(current_delta):.2f} > Band: {float(band):.2f})"
                })
        
        return {"status": "REBALANCE" if signals else "NORMAL", "signals": signals}

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


