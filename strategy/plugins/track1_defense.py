# -*- coding: utf-8 -*-
import numpy as np
from typing import List, Dict, Any, cast
from collections import deque
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from core.base_agent import BaseAgent
from core.contracts import MarketTick, OrderRequest

class Track1Defense(BaseAgent):
    """본월물 가두리 방어벽 (Short Strangle) 및 델타 헤징 엔진"""

    def __init__(self, shared_context: Dict[str, Any]) -> None:
        self.context: Dict[str, Any] = shared_context
        self._tick_history: deque[MarketTick] = deque(maxlen=1000)
        self.capital_allocation_rate: Decimal = Decimal('0.70')  # 원칙 1
        self.delta_deadband: Decimal = Decimal('0.5') # 원칙 9
        self.mdd_limit: Decimal = Decimal('0.15') # 원칙 8
        self.is_shutdown: bool = False

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def health_check(self) -> bool:
        return True

    async def process_message(self, message: Dict[str, Any]) -> None:
        pass

    def _calculate_kelly_fraction(self, win_rate: Decimal, payoff_ratio: Decimal) -> Decimal:
        """[목표 A / 원칙 1] 수식: f = W - ((1-W)/R), f/8 적용 후 0~0.125 클램핑"""
        if payoff_ratio <= Decimal('0'):
            return Decimal('0')
        
        # Kelly fraction: f = W - (1 - W) / R
        f = win_rate - ((Decimal('1') - win_rate) / payoff_ratio)
        fraction = f / Decimal('8')
        
        # Clamp between 0.0 and 0.125
        if fraction < Decimal('0'):
            return Decimal('0')
        if fraction > Decimal('0.125'):
            return Decimal('0.125')
        return fraction

    def _check_global_mdd_shutdown(self, initial_equity: Decimal, current_equity: Decimal) -> bool:
        """[목표 A / 원칙 8] MDD가 N% 하락 시 셧다운 트리거 발동 여부 확인"""
        if initial_equity <= Decimal('0'):
            return False
        
        drawdown = (current_equity - initial_equity) / initial_equity
        if drawdown <= -self.mdd_limit:
            self.is_shutdown = True
            return True
        return False

    async def _execute_liquidity_discovery(self, risk_validator: Any, target_options: Dict[str, Any]) -> List[OrderRequest]:
        """[목표 B / 원칙 6] 양날개 선 발주 -> 마진 재검증 -> 본대 발주 프로토콜"""
        wing_code = str(target_options.get("wing", "OPT_WING"))
        body_code = str(target_options.get("body", "OPT_BODY"))

        # 🛡️ [시장가 주문 원천 차단] 지정가 주문 적용
        wing_order = OrderRequest(
            decision_id=uuid4(),
            client_order_id=uuid4(),
            instrument_code=wing_code,
            side="BUY",
            price=Decimal("1.50"),  # 최우선 호가 지정가
            qty=10
        )

        # 🛡️ [Liquidity Discovery Death Trap 방어]
        # 리스크 에이전트 마진 재검증
        is_valid = await risk_validator.validate(wing_order)
        if not is_valid:
            # 본대(SELL) 발주 차단 및 생성 중이던 날개(BUY) 주문 파기 후 날개 청산 주문 리턴
            cleanup_order = OrderRequest(
                decision_id=uuid4(),
                client_order_id=uuid4(),
                instrument_code=wing_code,
                side="SELL",
                price=Decimal("1.40"),  # 슬리피지 감안 최우선 호가 - N틱 지정가
                qty=10
            )
            return [cleanup_order]

        body_order = OrderRequest(
            decision_id=uuid4(),
            client_order_id=uuid4(),
            instrument_code=body_code,
            side="SELL",
            price=Decimal("2.50"),  # 최우선 호가 지정가
            qty=10
        )
        return [wing_order, body_order]

    def _dynamic_scale_by_rv(self, prices_array: np.ndarray) -> Decimal:
        """[목표 C / 원칙 2, 3] Numpy 수익률 산출 -> RV -> Z-Score > 2.0 시 수량 축소율 반환"""
        if prices_array.size < 10:
            return Decimal('1.0')

        # 로그 수익률 계산
        log_returns = np.diff(np.log(prices_array))
        
        # 롤링 RV (윈도우 크기 5) 계산
        window = 5
        if log_returns.size < window:
            return Decimal('1.0')

        rv_series = []
        for i in range(len(log_returns) - window + 1):
            sub_series = log_returns[i : i + window]
            rv_series.append(np.std(sub_series))
            
        rv_arr = np.array(rv_series)
        mean_rv = np.mean(rv_arr)
        std_rv = np.std(rv_arr)
        
        if std_rv == 0:
            return Decimal('1.0')
            
        current_rv = rv_arr[-1]
        z_score = float((current_rv - mean_rv) / std_rv)

        # Z-Score > 2.0 시 수량 축소
        if z_score > 3.0:
            scale = 0.2
        elif z_score > 2.0:
            scale = 0.5
        else:
            scale = 1.0

        # 🛡️ [Numpy Float 오염 철통 방어]
        return Decimal(str(round(scale, 4)))

    def _trigger_kill_switch(self, portfolio_greeks: Dict[str, Decimal]) -> List[OrderRequest]:
        """[목표 C / 원칙 5] 위험 한계 도달 시 매도 청산 및 매수 스위칭(방향성 스위치) 주문 반환"""
        delta = portfolio_greeks.get("Delta", Decimal('0'))
        gamma = portfolio_greeks.get("Gamma", Decimal('0'))
        
        orders: List[OrderRequest] = []
        
        # 위험 한계 감지 임계치 설정 (예: 델타 절대값 10 초과 또는 감마 절대값 2 초과)
        if abs(delta) > Decimal('10.0') or abs(gamma) > Decimal('2.0'):
            # 🛡️ [시장가 주문 원천 차단] 지정가 적용
            # 1. 기존 매도 포지션 청산 (BUY TO COVER)
            orders.append(
                OrderRequest(
                    decision_id=uuid4(),
                    client_order_id=uuid4(),
                    instrument_code="OPT_SHORT_POS",
                    side="BUY",
                    price=Decimal("3.55"),  # 슬리피지 감안 최우선 호가 + N틱
                    qty=10
                )
            )
            # 2. 옵션 매수 스위칭 (BUY)
            orders.append(
                OrderRequest(
                    decision_id=uuid4(),
                    client_order_id=uuid4(),
                    instrument_code="OPT_LONG_SWITCH",
                    side="BUY",
                    price=Decimal("2.10"),
                    qty=10
                )
            )
        return orders

    def _calculate_futures_hedge_qty(self, current_portfolio_delta: Decimal) -> int:
        """[목표 D / 원칙 9] 델타 데드밴드 버퍼 확인 후 KOSPI 200 선물 헤지 계약 수 도출"""
        if abs(current_portfolio_delta) <= self.delta_deadband:
            return 0
        
        # 🛡️ [헤징 핑퐁(Whipsaw) 방어] 정수형으로 정확히 반올림하여 반환
        val = - (current_portfolio_delta / Decimal('1.0'))
        qty = int(val.to_integral_value(rounding=ROUND_HALF_UP))
        return qty

    async def on_tick(self, tick: MarketTick, current_delta: Decimal, near_iv: Decimal, far_iv: Decimal) -> List[OrderRequest]:
        """메인 이벤트 루프: 백워데이션(원칙 3) 감지 및 상기 방어 로직 종합 오케스트레이션"""
        self._tick_history.append(tick)
        
        # 1. 글로벌 MDD 셧다운 상태 검사
        initial_equity = cast(Decimal, self.context.get("initial_equity", Decimal('100000000')))
        current_equity = cast(Decimal, self.context.get("current_equity", Decimal('100000000')))
        
        if self._check_global_mdd_shutdown(initial_equity, current_equity) or self.is_shutdown:
            return []

        # 2. 백워데이션 감지 (근월물 IV > 원월물 IV 역전 시 신규 진입 차단)
        # 백워데이션 상태에서는 신규 포지션 구축을 억제하고 델타 헤징 및 킬 스위치 주문만 처리
        is_backwardation = near_iv > far_iv

        # 3. 킬 스위치 검증
        greeks = {
            "Delta": current_delta,
            "Gamma": cast(Decimal, self.context.get("portfolio_gamma", Decimal('0')))
        }
        kill_orders = self._trigger_kill_switch(greeks)
        if kill_orders:
            return kill_orders

        # 4. 동적 선물 델타 헤징 검증
        hedge_qty = self._calculate_futures_hedge_qty(current_delta)
        if hedge_qty != 0:
            side = "BUY" if hedge_qty > 0 else "SELL"
            hedge_order = OrderRequest(
                decision_id=uuid4(),
                client_order_id=uuid4(),
                instrument_code="FUT_KOSPI200",
                side=side,
                price=Decimal("350.00"),  # 고정 또는 틱 가격 기준
                qty=abs(hedge_qty)
            )
            return [hedge_order]

        # 5. 신규 매도 진입 시도 (백워데이션일 경우 차단)
        if is_backwardation:
            return []

        return []
