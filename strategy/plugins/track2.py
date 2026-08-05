# -*- coding: utf-8 -*-
import numpy as np
from typing import List, Dict, Any, Optional
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta
from uuid import uuid4

from core.base_agent import BaseAgent
from core.contracts import MarketTick, OrderRequest
from infra.time_service import TimeService
from strategy.common import TradingDateResetHelper

class Track2(BaseAgent):
    """
    [Track2] 데일리 함정(Trap) 기습 공격 및 4중 휩쏘 검증 엔진 (Track 2 Asymmetric Trap)
    - 자본 배분: 10% (비대칭 트랩 및 동적 헷지 모듈)
    """

    def __init__(self, shared_context: Optional[Dict[str, Any]] = None, time_service: Optional[TimeService] = None, config: Optional[Dict[str, Any]] = None) -> None:
        self.context: Dict[str, Any] = shared_context if shared_context is not None else (config or {})
        self.time_service: TimeService = time_service if time_service is not None else TimeService()
        self.capital_allocation_rate: Decimal = Decimal('0.10')  # 자본의 10% 할당
        
        self.trap_state: Dict[str, Any] = {"is_active": False, "entry_price": None, "entry_order": None}
        self._last_loss_time: Optional[datetime] = None
        self._daily_entry_count: int = 0
        self._max_daily_entries: int = 2
        self._cooldown_duration: timedelta = timedelta(minutes=15)
        self.date_reset_helper = TradingDateResetHelper()

    def build_asymmetric_trap(self, current_atm: float) -> Dict[str, Any]:
        """[Track2] 비대칭 양매수 및 프리미엄 수취 함정 구조 생성"""
        self.trap_state["is_active"] = True
        return {
            "status": "SUCCESS",
            "signals": [
                {
                    "action": "EXECUTE_SHORT_LEG",
                    "strikes": {"call": current_atm + 7.5, "put": current_atm - 7.5}
                },
                {
                    "action": "EXECUTE_LONG_TRAP_LEG",
                    "strikes": {"call": current_atm + 2.5, "put": current_atm - 2.5}
                }
            ]
        }

    def evaluate_trap_status(self, current_price: float) -> Dict[str, Any]:
        """
        [Track2] 트랩 상태 실시간 평가 및 헷지/손절/익절 시그널 산출
        - 손절(-30% 이상 손실): _last_loss_time 갱신(15분 쿨다운 발동) 및 손절 시그널 생성
        - 익절(+50% 이상 이익): _generate_reversal_short_orders 매도 스위칭 주문 생성
        """
        if not self.trap_state.get("is_active") or self.trap_state.get("entry_price") is None:
            return {"status": "NORMAL", "signals": []}

        entry_price = float(self.trap_state["entry_price"])
        if entry_price <= 0:
            return {"status": "NORMAL", "signals": []}

        pnl_ratio = (current_price - entry_price) / entry_price
        current_time = self.time_service.get_current_time()

        # 1. 손절 조건 (-30% 이하 손실)
        if pnl_ratio <= -0.30:
            self._last_loss_time = current_time
            self.trap_state["is_active"] = False
            self.trap_state["entry_price"] = None
            return {
                "status": "STOP_LOSS",
                "signals": [
                    {
                        "action": "STOP_LOSS_CLOSE",
                        "price": current_price,
                        "reason": f"Track2 손절 발동 (수익률: {pnl_ratio*100:.1f}%)"
                    }
                ]
            }

        # 2. 익절 조건 (+50% 이상 이익) -> 고점 IV 수확을 위한 매도(Short) 스위칭
        if pnl_ratio >= 0.50:
            self.trap_state["is_active"] = False
            self.trap_state["entry_price"] = None
            last_order = self.trap_state.get("entry_order")
            
            reversal_orders: List[OrderRequest] = []
            if last_order is not None:
                reversal_orders = self._generate_reversal_short_orders(
                    last_order, Decimal(str(current_price))
                )

            return {
                "status": "TAKE_PROFIT",
                "signals": [
                    {
                        "action": "TAKE_PROFIT_REVERSAL",
                        "price": current_price,
                        "reversal_orders": reversal_orders,
                        "reason": f"Track2 익절 및 매도 스위칭 (수익률: +{pnl_ratio*100:.1f}%)"
                    }
                ]
            }

        return {"status": "NORMAL", "signals": []}

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def health_check(self) -> bool:
        return True

    async def process_message(self, message: Dict[str, Any]) -> None:
        pass

    def _check_market_trigger(self, bbw_window: np.ndarray, volume_window: np.ndarray) -> bool:
        """[원칙 1] BBW 역사적 최저 스퀴즈 및 5분 거래량 Z-Score > 3.0 동시 만족 여부 산출"""
        if bbw_window.size < 2 or volume_window.size < 2:
            return False

        # 1. BBW 역사적 최저치 (Squeeze) 조건 검사
        is_bbw_squeeze = bool(bbw_window[-1] == np.min(bbw_window))

        # 2. 5분 거래량 Z-Score 계산 (마지막 값 제외한 평균 및 편차 활용)
        history_vols = volume_window[:-1]
        mean_vol = np.mean(history_vols)
        std_vol = np.std(history_vols)

        if std_vol == 0:
            if volume_window[-1] > mean_vol:
                z_score = 99.0
            else:
                z_score = 0.0
        else:
            z_score = float((volume_window[-1] - mean_vol) / std_vol)

        is_volume_explosion = z_score > 3.0

        return is_bbw_squeeze and is_volume_explosion

    def _validate_whipsaw_filters(self, tick: MarketTick, basis: Decimal, near_iv: Decimal, far_iv: Decimal, poc_price: Decimal) -> bool:
        """[원칙 2] 4중 미시구조 필터(OBI > 0.5, 베이시스, IV 스큐 엇박자 차단, POC 관통) 교차 검증"""
        # 1. 호가창 잔량 불균형 (OBI)
        bid_sum = sum(tick.bid_qtys[:5])
        ask_sum = sum(tick.ask_qtys[:5])
        if bid_sum + ask_sum == 0:
            obi_val = 0.0
        else:
            obi_val = (bid_sum - ask_sum) / (bid_sum + ask_sum)

        # 🛡️ [Numpy Float 감염 방어] Decimal 캐스팅
        obi = Decimal(str(obi_val))
        if abs(obi) <= Decimal('0.5'):
            return False

        # 2. KOSPI 200 베이시스 과열 검증 (Contango 임계값 0.3pt 초과 여부 검사)
        if basis <= Decimal('0.3'):
            return False

        # 3. 변동성 스큐 (IV Skew) 엇박자 차단
        # 지수 돌파 방향 판정
        is_upward = tick.last_price > poc_price
        
        # near_iv = 풋 IV, far_iv = 콜 IV 로 가정할 때의 엇박자 판단
        # 상방 돌파인데 풋 IV(near_iv)가 콜 IV(far_iv)보다 높거나 같으면 엇박자 (가짜 돌파)
        if is_upward and near_iv >= far_iv:
            return False
        # 하방 돌파인데 콜 IV(far_iv)가 풋 IV(near_iv)보다 높거나 같으면 엇박자 (가짜 돌파)
        if not is_upward and far_iv >= near_iv:
            return False

        # 4. 볼륨 프로파일 POC 관통 검증
        # POC 매물대를 충분히 관통(이탈)했는지 검증
        if abs(tick.last_price - poc_price) <= Decimal('1.0'):
            return False

        return True

    def _generate_reversal_short_orders(self, completed_long_order: Any, current_bbo_price: Decimal) -> List[OrderRequest]:
        """[원칙 3] 매수 옵션 익절 완료 즉시 고점 IV 수확을 위한 매도(Short) 스위칭 주문 생성 (틱사이즈 및 최소가격 보정)"""
        # 🛡️ [역전환 스위칭 지정가 강제] 지정가(IOC) 적용 및 슬리피지 마진 차감
        # KOSPI 200 옵션 틱 사이즈 테이블 적용: 3.0 미만은 0.01, 3.0 이상은 0.05
        # 매도 주문이므로 체결 확률을 높이기 위해 BBO 가격보다 2틱 낮은 가격 제시
        tick_size = Decimal('0.01') if current_bbo_price < Decimal('3.0') else Decimal('0.05')
        price = current_bbo_price - Decimal('2') * tick_size
        
        # 틱사이즈 단위로 가격을 정확히 절사(Quantize) 및 최저가 클램핑 적용
        price = (price / tick_size).to_integral_value(rounding=ROUND_HALF_UP) * tick_size
        price = max(price, Decimal('0.01'))
        
        inst_code = str(getattr(completed_long_order, "instrument_code", "OPT_TRAP"))
        qty = int(getattr(completed_long_order, "qty", 10))

        reversal_order = OrderRequest(
            decision_id=uuid4(),
            client_order_id=uuid4(),
            instrument_code=inst_code,
            side="SELL",
            price=price,
            qty=qty
        )
        return [reversal_order]

    async def on_tick(self, tick: MarketTick, bbw_data: np.ndarray, vol_data: np.ndarray, basis: Decimal, near_iv: Decimal, far_iv: Decimal, poc_price: Decimal) -> List[OrderRequest]:
        """메인 이벤트 핸들러: 쿨다운 타이머 체크, 방아쇠 검증, 4중 필터 통과 시 기습 함정 발주"""
        current_time = self.time_service.get_current_time()

        # 영업일 변경 세션 감지 및 일일 진입 횟수 리셋
        if self.date_reset_helper.check_and_update(current_time.date()):
            self._daily_entry_count = 0

        # 🛡️ [논블로킹 쿨다운 철저 수호] 15분 하드웨어 쿨다운 가드 검사
        if self._last_loss_time is not None:
            if current_time - self._last_loss_time < self._cooldown_duration:
                return []

        # 일일 최대 진입 횟수 제한 검사
        if self._daily_entry_count >= self._max_daily_entries:
            return []

        # 1. 정량적 방아쇠 검사 (BBW 스퀴즈 및 거래량 폭발)
        if not self._check_market_trigger(bbw_data, vol_data):
            return []

        # 2. 4중 미시구조 필터 교차 검증
        if not self._validate_whipsaw_filters(tick, basis, near_iv, far_iv, poc_price):
            return []

        # 3. 매수 지정가(IOC) 주문 생성
        # BBO보다 약간 높은 가격에 진입하여 빠른 매수 체결 도모
        price = tick.last_price + Decimal('0.10')
        entry_order = OrderRequest(
            decision_id=uuid4(),
            client_order_id=uuid4(),
            instrument_code=tick.instrument_code,
            side="BUY",
            price=price,
            qty=10
        )

        self.trap_state["is_active"] = True
        self.trap_state["entry_price"] = tick.last_price
        self.trap_state["entry_order"] = entry_order
        self._daily_entry_count += 1
        return [entry_order]


# 하위 호환성을 위한 전략 클래스 별칭
Track2 = Track2


