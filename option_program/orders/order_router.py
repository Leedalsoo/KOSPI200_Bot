"""Production Order Router & Stale Order Management.

Provides:
- BrokerMode-aware Order Routing (PAPER / SHADOW / REAL)
- Stale Order Detection & Auto-Cancel Timeout Guard
- Seamless Integration with OmsFsm & RiskApprovalToken
"""
from dataclasses import dataclass
from typing import Dict, Any, Optional, List, Tuple, Set
import logging
import time
import uuid

from shared.contracts.canonical import (
    CanonicalOrderCommand,
    CanonicalExecutionReport,
    CanonicalAssetType,
    CanonicalOrderSide
)
from shared.core.contracts import OrderStatus, RiskApprovalToken
from option_program.orders.oms_fsm import OmsFsm

logger = logging.getLogger(__name__)

class OrderRouter:
    """[주문 라우터] OMS FSM 및 브로커 계층 간의 주문 발주, 상태 전이, 미체결 타임아웃 관리"""

    def __init__(self, fsm: Optional[OmsFsm] = None, stale_timeout_sec: float = 30.0):
        self.fsm = fsm or OmsFsm()
        self.stale_timeout_sec = stale_timeout_sec
        # order_id -> (command, submitted_timestamp)
        self._active_orders: Dict[uuid.UUID, Tuple[CanonicalOrderCommand, float]] = {}
        # 멱등성 및 재사용 방지용 처리된 토큰/주문 식별자 추적
        self._processed_tokens: Set[str] = set()
        self._processed_order_ids: Set[uuid.UUID] = set()

    def validate_token(self, command: CanonicalOrderCommand, token: Any) -> Tuple[bool, Optional[str]]:
        """RiskApprovalToken의 유효성, 위변조 여부, 일치성 및 재사용 여부 검증."""
        if token is None:
            return False, "TOKEN_MISSING"

        if not hasattr(token, "order_id") or not hasattr(token, "signature"):
            return False, "TOKEN_INVALID_TYPE"

        order_id = getattr(token, "order_id", None)
        if not isinstance(order_id, uuid.UUID):
            try:
                if not order_id or not uuid.UUID(str(order_id)):
                    return False, "TOKEN_INVALID_ORDER_ID"
            except Exception:
                return False, "TOKEN_INVALID_ORDER_ID"

        # 멱등성 / 재사용 검사
        token_key = f"{order_id}_{token.signature}"
        if token_key in self._processed_tokens or order_id in self._processed_order_ids:
            return False, "TOKEN_ALREADY_USED"

        # 서명 및 주문 일치성 검증
        expected_sig = f"SIG-RISK-APPROVED-{command.track_id}-{command.client_order_id}"
        if token.signature != expected_sig and (command.client_order_id not in token.signature or command.track_id not in token.signature):
            return False, "TOKEN_SIGNATURE_MISMATCH"

        return True, None

    def register_and_route(
        self,
        command: CanonicalOrderCommand,
        token: RiskApprovalToken,
        broker_adapter: Any = None,
        mode_str: str = "PAPER"
    ) -> Optional[uuid.UUID]:
        """RiskApprovalToken 검증 후 주문 FSM 등록 및 브로커 전송 파이프라인"""
        # 1. RiskApprovalToken 유효성 및 일관성 엄격 검증
        is_valid, reason = self.validate_token(command, token)
        if not is_valid:
            logger.warning(f"[OrderRouter] Rejected order {getattr(command, 'client_order_id', 'UNKNOWN')}: {reason}")
            if token is not None and hasattr(token, "order_id") and isinstance(token.order_id, uuid.UUID):
                self.fsm.states[token.order_id] = OrderStatus.REJECTED
            return None

        order_id = token.order_id
        # 토큰 사용 기록 (재사용 방어)
        token_key = f"{order_id}_{token.signature}"
        self._processed_tokens.add(token_key)
        self._processed_order_ids.add(order_id)

        # 2. OMS 상태 등록 (NEW -> VALIDATED -> SENT)
        self.fsm.states[order_id] = OrderStatus.NEW
        self.fsm.states[order_id] = OrderStatus.VALIDATED
        self.fsm.states[order_id] = OrderStatus.SENT
        self._active_orders[order_id] = (command, time.time())

        # 3. Broker Adapter 실제 호출 (broker_adapter가 제공된 경우)
        if broker_adapter is not None:
            try:
                report: Optional[CanonicalExecutionReport] = broker_adapter.send_order(command)
                if report is not None and getattr(report, "executed_qty", 0) > 0:
                    self.fsm.states[order_id] = OrderStatus.FILLED
                    self._active_orders.pop(order_id, None)
                    logger.info(f"[OrderRouter] Order {command.client_order_id} (UUID: {order_id}) executed via {mode_str} Broker: FILLED qty={report.executed_qty}")
                else:
                    self.fsm.states[order_id] = OrderStatus.REJECTED
                    self._active_orders.pop(order_id, None)
                    logger.warning(f"[OrderRouter] Order {command.client_order_id} (UUID: {order_id}) rejected/failed at {mode_str} Broker.")
            except Exception as exc:
                self.fsm.states[order_id] = OrderStatus.REJECTED
                self._active_orders.pop(order_id, None)
                logger.error(f"[OrderRouter] Exception while sending order {command.client_order_id} to {mode_str} Broker: {exc}")
        else:
            logger.info(f"[OrderRouter] Order {command.client_order_id} (UUID: {order_id}) queued/routed to {mode_str} Broker.")

        return order_id


    def handle_execution_report(
        self,
        order_id: uuid.UUID,
        report: CanonicalExecutionReport
    ) -> None:
        """체결 보고서 수신에 따른 FSM 상태 전이"""
        if report.executed_qty > 0:
            self.fsm.states[order_id] = OrderStatus.FILLED
            self._active_orders.pop(order_id, None)
            logger.info(f"[OrderRouter] Order {order_id} FILLED: {report.executed_qty}@{report.executed_price}")
        else:
            self.fsm.states[order_id] = OrderStatus.REJECTED
            self._active_orders.pop(order_id, None)
            logger.warning(f"[OrderRouter] Order {order_id} REJECTED by Broker.")

    def scan_stale_orders(self, current_time: Optional[float] = None) -> List[uuid.UUID]:
        """지정된 타임아웃(30초)을 초과한 미체결/대기 주문 감지"""
        now = current_time if current_time is not None else time.time()
        stale_order_ids: List[uuid.UUID] = []

        for order_id, (cmd, sub_time) in list(self._active_orders.items()):
            status = self.fsm.get_status(order_id)
            if status in (OrderStatus.SENT, OrderStatus.ACCEPTED, OrderStatus.PENDING):
                if (now - sub_time) >= self.stale_timeout_sec:
                    stale_order_ids.append(order_id)
                    logger.warning(f"[OrderRouter] Stale order detected: {order_id} (Elapsed: {now - sub_time:.1f}s >= {self.stale_timeout_sec}s)")

        return stale_order_ids

    def cancel_stale_order(self, order_id: uuid.UUID) -> bool:
        """미체결 지연 주문 강제 취소 전이"""
        if order_id in self._active_orders:
            self.fsm.states[order_id] = OrderStatus.CANCELLED
            self._active_orders.pop(order_id, None)
            logger.info(f"[OrderRouter] Stale order {order_id} CANCELLED safely.")
            return True
        return False
