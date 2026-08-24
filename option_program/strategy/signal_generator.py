"""Production Signal Generator Architecture.

Bridges Strategy Tracks (1~9) to Order Commands with:
- Strict Schema & Field Validation (Asset type, side, qty, price, strike, reason)
- Signal De-duplication & Debounce Idempotency
- Malformed Signal Defense (Negative price, zero qty, empty tag)
- Safe Conversion to CanonicalOrderCommand
"""
from dataclasses import dataclass
from typing import Dict, Any, Optional, Set, Tuple
import logging
import time
import uuid

from shared.contracts.canonical import (
    CanonicalStrategySignal,
    CanonicalOrderCommand,
    CanonicalAssetType,
    CanonicalOrderSide,
    CanonicalOptionType
)

logger = logging.getLogger(__name__)

class SignalGenerator:
    """[신호 생성기] 전략 1~9의 판단 결과를 수집하여 검증, 중복 제거 후 주문 명령으로 정규화 변환"""

    def __init__(self, debounce_window_sec: float = 0.5):
        self.debounce_window_sec = debounce_window_sec
        # signal_fingerprint -> last_emitted_timestamp
        self._emitted_signals: Dict[str, float] = {}

    def _generate_fingerprint(self, signal: CanonicalStrategySignal) -> str:
        """신호 내용 기반 고유 지문 생성 (중복 디바운싱용)"""
        return f"{signal.track_id}_{signal.asset_type.value}_{signal.side.value}_{signal.strike}_{signal.option_type.value if signal.option_type else 'NONE'}_{signal.tag_id}"

    def validate_signal(self, signal: CanonicalStrategySignal) -> Tuple[bool, Optional[str]]:
        """신호 유효성 및 필수 필드 전수 검증"""
        # 1. 수량 검증
        if signal.qty <= 0:
            return False, f"INVALID_QTY: {signal.qty} <= 0"

        # 2. 가격 검증 (음수 불가, 극단적 비정상 가격 방어)
        if signal.price <= 0.0:
            return False, f"INVALID_PRICE: {signal.price} <= 0"

        # 3. 필수 태그 및 트랙 ID 검증
        if not signal.track_id:
            return False, "MISSING_TRACK_ID"

        if not signal.tag_id:
            return False, "MISSING_TAG_ID"

        # 4. 옵션 자산의 경우 strike 및 option_type 필수
        if signal.asset_type == CanonicalAssetType.OPTION:
            if signal.strike <= 0.0:
                return False, f"INVALID_OPTION_STRIKE: {signal.strike}"
            if signal.option_type is None:
                return False, "MISSING_OPTION_TYPE"

        return True, None

    def is_duplicate(self, signal: CanonicalStrategySignal, current_time: Optional[float] = None) -> bool:
        """동일 조건 신호의 디바운스 윈도우 내 중복 여부 확인"""
        now = current_time if current_time is not None else time.time()
        fp = self._generate_fingerprint(signal)

        last_time = self._emitted_signals.get(fp)
        if last_time is not None and (now - last_time) < self.debounce_window_sec:
            logger.debug(f"[SignalGenerator] Duplicate signal suppressed: {fp} (elapsed {now - last_time:.3f}s)")
            return True

        self._emitted_signals[fp] = now
        return False

    def process_signal(
        self,
        signal: CanonicalStrategySignal,
        current_time: Optional[float] = None
    ) -> Optional[CanonicalOrderCommand]:
        """신호 검증 ➔ 중복 제거 ➔ CanonicalOrderCommand 변환 파이프라인"""
        # 1. 유효성 검증
        is_valid, reason = self.validate_signal(signal)
        if not is_valid:
            logger.warning(f"[SignalGenerator] Signal Rejected: {reason} | Signal: {signal}")
            return None

        # 2. 중복 디바운싱 검사
        if self.is_duplicate(signal, current_time=current_time):
            return None

        # 3. CanonicalOrderCommand 변환
        client_order_id = f"ORD-{signal.track_id}-{int(time.time()*1000)}-{uuid.uuid4().hex[:6]}"
        cmd = CanonicalOrderCommand(
            client_order_id=client_order_id,
            track_id=signal.track_id,
            asset_type=signal.asset_type,
            side=signal.side,
            qty=signal.qty,
            price=signal.price,
            option_type=signal.option_type,
            strike=signal.strike,
            tag_id=signal.tag_id
        )

        logger.debug(f"[SignalGenerator] Signal Accepted -> OrderCommand {client_order_id} ({signal.track_id} {signal.side.value} {signal.qty}@{signal.price})")
        return cmd

    def clear_history(self) -> None:
        """디바운스 캐시 초기화"""
        self._emitted_signals.clear()
