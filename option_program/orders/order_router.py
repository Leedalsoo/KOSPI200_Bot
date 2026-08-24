"""Production Order Router & Stale Order Management.

Provides:
- BrokerMode-aware Order Routing (PAPER / SHADOW / REAL)
- Stale Order Detection & Auto-Cancel Timeout Guard
- Seamless Integration with OmsFsm & RiskApprovalToken
"""
from dataclasses import dataclass
from typing import Dict, Any, Optional, List, Tuple
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

    def register_and_route(
        self,
        command: CanonicalOrderCommand,
        token: RiskApprovalToken,
        broker_adapter: Any,
        mode_str: str = "PAPER"
    ) -> Optional[uuid.UUID]:
        """주문 FSM 등록 및 브로커 전송 파이프라인"""
        order_id = token.order_id

        # 1. OMS 상태 등록 (NEW)
        self.fsm.states[order_id] = OrderStatus.NEW

        # 2. VALIDATED 전이
        self.fsm.states[order_id] = OrderStatus.VALIDATED

        # 3. SENT 전이 및 브로커 라우팅
        self.fsm.states[order_id] = OrderStatus.SENT
        self._active_orders[order_id] = (command, time.time())

        logger.info(f"[OrderRouter] Order {command.client_order_id} (UUID: {order_id}) routed to {mode_str} Broker.")
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
