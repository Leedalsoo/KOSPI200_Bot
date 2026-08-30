"""Production Order Router & Stale Order Management.

Provides:
- BrokerMode-aware Order Routing (PAPER / SHADOW / REAL)
- Stale Order Detection & Auto-Cancel Timeout Guard
- Seamless Integration with OmsFsm & RiskApprovalToken
"""
from dataclasses import dataclass
from typing import Dict, Any, Optional, List, Tuple, Set
import logging
import threading
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
        self._lock = threading.Lock()
        # order_id -> (command, submitted_timestamp)
        self._active_orders: Dict[uuid.UUID, Tuple[CanonicalOrderCommand, float]] = {}
        # order_id -> broker_adapter
        self._order_brokers: Dict[uuid.UUID, Any] = {}
        # order_id -> cumulative executed quantity
        self._cum_executed_qty: Dict[uuid.UUID, int] = {}
        # 멱등성 및 재사용 방지용 처리된 토큰/주문 식별자 추적
        self._processed_tokens: Set[str] = set()
        self._processed_order_ids: Set[uuid.UUID] = set()
        # [8단계-2] 주문 추적 권위 저장소: client_order_id / order_uuid ↔ broker_order_id 매핑
        self._order_to_broker_id: Dict[uuid.UUID, str] = {}
        self._client_to_broker_id: Dict[str, str] = {}
        self._broker_to_client_id: Dict[str, str] = {}
        # [8단계-3] 주문별 실제 체결수량 권위 저장소 (미체결/부분체결/완료체결 전수 보존)
        self._executed_qty_history: Dict[uuid.UUID, int] = {}
        self._client_to_executed_qty: Dict[str, int] = {}

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
        with self._lock:
            # 1. RiskApprovalToken 유효성 및 일관성 엄격 검증
            is_valid, reason = self.validate_token(command, token)
            if not is_valid:
                logger.warning(f"[OrderRouter] Rejected order {getattr(command, 'client_order_id', 'UNKNOWN')}: {reason}")
                # 중복 주문(TOKEN_ALREADY_USED) 거부 시 기존 정상 주문의 FSM 상태를 훼손하지 않음
                if reason != "TOKEN_ALREADY_USED":
                    if token is not None and hasattr(token, "order_id") and isinstance(token.order_id, uuid.UUID):
                        self.fsm.transition_sync(token.order_id, OrderStatus.REJECTED)
                return None

            order_id = token.order_id
            # 토큰 사용 기록 (재사용 방어)
            token_key = f"{order_id}_{token.signature}"
            self._processed_tokens.add(token_key)
            self._processed_order_ids.add(order_id)

            # 2. OMS 상태 등록 (None -> NEW -> VALIDATED -> SENT)
            self.fsm.transition_sync(order_id, OrderStatus.NEW)
            self.fsm.transition_sync(order_id, OrderStatus.VALIDATED)
            self.fsm.transition_sync(order_id, OrderStatus.SENT)
            self._active_orders[order_id] = (command, time.time())
            self._cum_executed_qty[order_id] = 0
            if broker_adapter is not None:
                self._order_brokers[order_id] = broker_adapter

            # 3. [Broker 실행책임 단일화] OrderRouter는 Broker를 직접 발주하지 않음.
            # 발주 실행 책임은 단일 오케스트레이터(TradingSystem in main.py)가 전담하며,
            # 체결 결과는 handle_execution_report()를 통해 수신하여 FSM 상태를 전이한다.
            logger.info(
                f"[OrderRouter] Order {command.client_order_id} (UUID: {order_id}) validated & registered to FSM (SENT). "
                f"Broker execution delegated to Orchestrator (TradingSystem)."
            )

            return order_id

    def handle_execution_report(
        self,
        order_id: uuid.UUID,
        report: CanonicalExecutionReport
    ) -> None:
        """체결 보고서 수신에 따른 FSM 상태 전이 및 누적 체결 관리"""
        with self._lock:
            cmd_info = self._active_orders.get(order_id)
            requested_qty = cmd_info[0].qty if cmd_info else None
            client_id = cmd_info[0].client_order_id if cmd_info else getattr(report, "client_order_id", None)
            prev_cum = self._cum_executed_qty.get(order_id, 0)
            new_cum = prev_cum + report.executed_qty

            if report.executed_qty > 0:
                if requested_qty is not None and new_cum > requested_qty:
                    self.fsm.transition_sync(order_id, OrderStatus.REJECTED)
                    self._active_orders.pop(order_id, None)
                    self._order_brokers.pop(order_id, None)
                    self._cum_executed_qty.pop(order_id, None)
                    logger.error(
                        f"[OrderRouter] Order {order_id} oversized execution rejected: "
                        f"cumulative_qty={new_cum} > requested_qty={requested_qty}"
                    )
                elif requested_qty is not None and new_cum < requested_qty:
                    self._cum_executed_qty[order_id] = new_cum
                    self._executed_qty_history[order_id] = new_cum
                    if client_id:
                        self._client_to_executed_qty[client_id] = new_cum
                    self.fsm.transition_sync(order_id, OrderStatus.PARTIAL)
                    logger.info(
                        f"[OrderRouter] Order {order_id} PARTIAL: {new_cum}/{requested_qty}@{report.executed_price}"
                    )
                elif requested_qty is not None and new_cum == requested_qty:
                    self._cum_executed_qty[order_id] = new_cum
                    self._executed_qty_history[order_id] = new_cum
                    if client_id:
                        self._client_to_executed_qty[client_id] = new_cum
                    self.fsm.transition_sync(order_id, OrderStatus.FILLED)
                    self._active_orders.pop(order_id, None)
                    self._order_brokers.pop(order_id, None)
                    self._cum_executed_qty.pop(order_id, None)
                    logger.info(f"[OrderRouter] Order {order_id} FILLED: {new_cum}@{report.executed_price}")
                else:
                    self.fsm.transition_sync(order_id, OrderStatus.REJECTED)
                    self._active_orders.pop(order_id, None)
                    self._order_brokers.pop(order_id, None)
                    self._cum_executed_qty.pop(order_id, None)
                    logger.warning(
                        f"[OrderRouter] Order {order_id} received execution report for inactive/unknown order: REJECTED."
                    )
            else:
                self.fsm.transition_sync(order_id, OrderStatus.REJECTED)
                self._active_orders.pop(order_id, None)
                self._order_brokers.pop(order_id, None)
                self._cum_executed_qty.pop(order_id, None)
                logger.warning(f"[OrderRouter] Order {order_id} REJECTED by Broker.")

    def get_executed_qty(self, order_identifier: Any) -> int:
        """[8단계-3] order_uuid 또는 client_order_id로부터 실제 체결수량 조회 (미체결/부분체결/완료체결 전수 지원)."""
        with self._lock:
            if isinstance(order_identifier, uuid.UUID):
                return self._executed_qty_history.get(order_identifier, self._cum_executed_qty.get(order_identifier, 0))
            client_id = str(order_identifier)
            return self._client_to_executed_qty.get(client_id, 0)

    def scan_stale_orders(self, current_time: Optional[float] = None) -> List[uuid.UUID]:
        """지정된 타임아웃(30초)을 초과한 미체결/대기 주문 감지"""
        with self._lock:
            now = current_time if current_time is not None else time.time()
            stale_order_ids: List[uuid.UUID] = []

            for order_id, (cmd, sub_time) in list(self._active_orders.items()):
                status = self.fsm.get_status(order_id)
                if status in (OrderStatus.SENT, OrderStatus.ACCEPTED, OrderStatus.PENDING, OrderStatus.PARTIAL):
                    if (now - sub_time) >= self.stale_timeout_sec:
                        stale_order_ids.append(order_id)
                        logger.warning(
                            f"[OrderRouter] Stale order detected: {order_id} "
                            f"(Elapsed: {now - sub_time:.1f}s >= {self.stale_timeout_sec}s)"
                        )

            return stale_order_ids

    def cancel_stale_order(self, order_id: uuid.UUID, broker_adapter: Optional[Any] = None) -> bool:
        """미체결 지연 주문 실제 Broker cancel_order() 호출 및 FSM 상태 전이"""
        with self._lock:
            if order_id not in self._active_orders:
                return False

            command, sub_time = self._active_orders[order_id]
            client_order_id = getattr(command, "client_order_id", str(order_id))
            broker = broker_adapter or self._order_brokers.get(order_id)

            if broker is not None:
                try:
                    cancelled = broker.cancel_order(client_order_id)
                    if cancelled:
                        self.fsm.transition_sync(order_id, OrderStatus.CANCELLED)
                        self._active_orders.pop(order_id, None)
                        self._order_brokers.pop(order_id, None)
                        self._cum_executed_qty.pop(order_id, None)
                        logger.info(f"[OrderRouter] Stale order {order_id} ({client_order_id}) CANCELLED safely via Broker.")
                        return True
                    else:
                        logger.warning(f"[OrderRouter] Broker failed to cancel stale order {order_id} ({client_order_id}).")
                        return False
                except Exception as exc:
                    logger.error(f"[OrderRouter] Exception while cancelling stale order {order_id} ({client_order_id}) via Broker: {exc}")
                    return False
            else:
                self.fsm.transition_sync(order_id, OrderStatus.CANCELLED)
                self._active_orders.pop(order_id, None)
                self._order_brokers.pop(order_id, None)
                self._cum_executed_qty.pop(order_id, None)
                logger.info(f"[OrderRouter] Stale order {order_id} CANCELLED safely (no broker attached).")
                return True

    def register_broker_order_id(self, order_identifier: Any, broker_order_id: str) -> None:
        """[8단계-2] 주문 접수 ACK 성공 시 client_order_id 또는 order_uuid와 broker_order_id 간의 양방향 매핑 등록."""
        with self._lock:
            if isinstance(order_identifier, uuid.UUID):
                order_uuid = order_identifier
                self._order_to_broker_id[order_uuid] = broker_order_id
                cmd_info = self._active_orders.get(order_uuid)
                if cmd_info:
                    client_id = cmd_info[0].client_order_id
                    self._client_to_broker_id[client_id] = broker_order_id
                    self._broker_to_client_id[broker_order_id] = client_id
            elif isinstance(order_identifier, str):
                client_id = order_identifier
                self._client_to_broker_id[client_id] = broker_order_id
                self._broker_to_client_id[broker_order_id] = client_id
                # active orders에서 일치하는 UUID 탐색하여 uuid 매핑도 동시 보존
                for u, (cmd, _) in self._active_orders.items():
                    if getattr(cmd, "client_order_id", None) == client_id:
                        self._order_to_broker_id[u] = broker_order_id
                        break

    def get_broker_order_id(self, order_identifier: Any) -> Optional[str]:
        """[8단계-2] order_uuid 또는 client_order_id로부터 broker_order_id 조회."""
        with self._lock:
            if isinstance(order_identifier, uuid.UUID):
                return self._order_to_broker_id.get(order_identifier)
            return self._client_to_broker_id.get(str(order_identifier))

    def get_client_order_id_by_broker_id(self, broker_order_id: str) -> Optional[str]:
        """[8단계-2] broker_order_id로부터 client_order_id 역방향 조회."""
        with self._lock:
            return self._broker_to_client_id.get(broker_order_id)

