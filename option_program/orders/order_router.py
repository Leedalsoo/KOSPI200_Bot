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

    def __init__(
        self,
        fsm: Optional[OmsFsm] = None,
        stale_timeout_sec: float = 30.0,
        wal_store: Optional[Any] = None,
    ):
        self.fsm = fsm or OmsFsm()
        self.stale_timeout_sec = stale_timeout_sec
        self.wal_store = wal_store
        self._lock = threading.RLock()
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
        # [8단계-5] Execution ID 중복수신 방어용 멱등성 저장소
        self._processed_exec_ids: Set[str] = set()

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

            # [D-15] Broker 전송 전 ORDER_INTENT WAL 영속화
            wal_success = self._persist_order_intent_wal(order_id, command)
            if not wal_success:
                logger.error(
                    f"[OrderRouter] Failed to persist ORDER_INTENT for {command.client_order_id}. "
                    f"Aborting order to prevent unrecoverable state."
                )
                self.fsm.transition_sync(order_id, OrderStatus.REJECTED)
                self._active_orders.pop(order_id, None)
                self._order_brokers.pop(order_id, None)
                self._cum_executed_qty.pop(order_id, None)
                return None

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
            # [8단계-5] Execution ID 중복수신 방어 (멱등성 보장)
            exec_id = getattr(report, "exec_id", None)
            if exec_id:
                if exec_id in self._processed_exec_ids:
                    logger.warning(
                        f"[OrderRouter] Duplicate execution report ignored (Idempotency): "
                        f"exec_id={exec_id}, order_id={order_id}"
                    )
                    return
                self._processed_exec_ids.add(exec_id)

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
                    self._persist_execution_wal(order_id, report, new_cum, requested_qty, OrderStatus.PARTIAL, client_id)
                    logger.info(
                        f"[OrderRouter] Order {order_id} PARTIAL: {new_cum}/{requested_qty}@{report.executed_price}"
                    )
                elif requested_qty is not None and new_cum == requested_qty:
                    self._cum_executed_qty[order_id] = new_cum
                    self._executed_qty_history[order_id] = new_cum
                    if client_id:
                        self._client_to_executed_qty[client_id] = new_cum
                    self.fsm.transition_sync(order_id, OrderStatus.FILLED)
                    self._persist_execution_wal(order_id, report, new_cum, requested_qty, OrderStatus.FILLED, client_id)
                    self._active_orders.pop(order_id, None)
                    self._order_brokers.pop(order_id, None)
                    self._cum_executed_qty.pop(order_id, None)
                    logger.info(f"[OrderRouter] Order {order_id} FILLED: {new_cum}@{report.executed_price}")
                else:
                    self.fsm.transition_sync(order_id, OrderStatus.REJECTED)
                    self._persist_execution_wal(order_id, report, new_cum, requested_qty, OrderStatus.REJECTED, client_id)
                    self._active_orders.pop(order_id, None)
                    self._order_brokers.pop(order_id, None)
                    self._cum_executed_qty.pop(order_id, None)
                    logger.warning(
                        f"[OrderRouter] Order {order_id} received execution report for inactive/unknown order: REJECTED."
                    )
            else:
                self.fsm.transition_sync(order_id, OrderStatus.REJECTED)
                self._persist_execution_wal(order_id, report, new_cum, requested_qty, OrderStatus.REJECTED, client_id)
                self._active_orders.pop(order_id, None)
                self._order_brokers.pop(order_id, None)
                self._cum_executed_qty.pop(order_id, None)
                logger.warning(f"[OrderRouter] Order {order_id} REJECTED by Broker.")

    def _persist_order_intent_wal(self, order_id: uuid.UUID, command: CanonicalOrderCommand) -> bool:
        """[D-15] 주문 생성 및 FSM 등록 시점에 ORDER_INTENT WAL 영속화"""
        if self.wal_store is None:
            return True

        try:
            side_val = getattr(command, "side", CanonicalOrderSide.BUY)
            side_str = side_val.value if hasattr(side_val, "value") else str(side_val)
            opt_val = getattr(command, "option_type", None)
            opt_str = opt_val.value if opt_val and hasattr(opt_val, "value") else (str(opt_val) if opt_val else None)

            event_data = {
                "order_id": str(order_id),
                "client_order_id": getattr(command, "client_order_id", ""),
                "track_id": getattr(command, "track_id", ""),
                "symbol": getattr(command, "symbol", ""),
                "side": side_str,
                "qty": getattr(command, "qty", 0),
                "price": float(getattr(command, "price", 0.0) or 0.0),
                "option_type": opt_str,
                "strike": float(getattr(command, "strike", 0.0) or 0.0),
                "timestamp": str(time.time()),
                "status": OrderStatus.SENT.value,
            }
            if hasattr(self.wal_store, "save_event_sync"):
                self.wal_store.save_event_sync("ORDER_INTENT", event_data)
            return True
        except Exception as exc:
            logger.error(f"[OrderRouter] Failed to persist ORDER_INTENT to WAL: {exc}")
            return False

    def persist_broker_send_started(self, command: CanonicalOrderCommand) -> bool:
        """[D-15] Broker API 전송 직전 BROKER_SEND_STARTED WAL 영속화"""
        if self.wal_store is None:
            return True

        try:
            client_id = getattr(command, "client_order_id", "")
            order_id = self.get_order_uuid_by_client_id(client_id)
            side_val = getattr(command, "side", CanonicalOrderSide.BUY)
            side_str = side_val.value if hasattr(side_val, "value") else str(side_val)

            event_data = {
                "client_order_id": client_id,
                "order_id": str(order_id) if order_id else None,
                "track_id": getattr(command, "track_id", ""),
                "symbol": getattr(command, "symbol", ""),
                "side": side_str,
                "qty": getattr(command, "qty", 0),
                "price": float(getattr(command, "price", 0.0) or 0.0),
                "timestamp": str(time.time()),
            }
            if hasattr(self.wal_store, "save_event_sync"):
                self.wal_store.save_event_sync("BROKER_SEND_STARTED", event_data)
            return True
        except Exception as exc:
            logger.error(f"[OrderRouter] Failed to persist BROKER_SEND_STARTED to WAL: {exc}")
            return False

    def get_order_uuid_by_client_id(self, client_order_id: str) -> Optional[uuid.UUID]:
        """[D-15] client_order_id로부터 active_orders 내의 order_uuid 조회"""
        with self._lock:
            for u, (cmd, _) in self._active_orders.items():
                if getattr(cmd, "client_order_id", None) == client_order_id:
                    return u
            return None

    def _persist_execution_wal(
        self,
        order_id: uuid.UUID,
        report: CanonicalExecutionReport,
        cum_qty: int,
        requested_qty: Optional[int],
        status: OrderStatus,
        client_id: Optional[str],
    ) -> None:
        """[D-10] 체결 이벤트 및 누적 체결 상태를 WAL 영속 저장소에 즉시 기록"""
        if self.wal_store is None:
            return

        try:
            event_type = (
                "PARTIAL_EXECUTION"
                if status == OrderStatus.PARTIAL
                else ("FILLED_EXECUTION" if status == OrderStatus.FILLED else "EXECUTION_REPORT")
            )
            event_data = {
                "exec_id": getattr(report, "exec_id", None),
                "order_id": str(order_id),
                "client_order_id": client_id or getattr(report, "client_order_id", None),
                "executed_qty": getattr(report, "executed_qty", 0),
                "cum_executed_qty": cum_qty,
                "requested_qty": requested_qty,
                "executed_price": getattr(report, "executed_price", 0.0),
                "status": status.value,
                "timestamp": getattr(report, "timestamp", str(time.time())),
            }
            if hasattr(self.wal_store, "save_event_sync"):
                self.wal_store.save_event_sync(event_type, event_data)
            elif hasattr(self.wal_store, "_sync_save"):
                import orjson

                payload = orjson.dumps(
                    {"event_type": event_type, "data": event_data},
                    default=str,
                    option=orjson.OPT_APPEND_NEWLINE,
                )
                self.wal_store._sync_save(payload)
        except Exception as exc:
            logger.error(f"[OrderRouter] Failed to persist execution to WAL: {exc}")

    def recover_from_wal(self, events: List[Dict[str, Any]]) -> int:
        """[D-10] WAL 이벤트 로그로부터 누적 체결 상태, 멱등성 exec_id, FSM 상태 복원"""
        with self._lock:
            recovered_count = 0
            for entry in events:
                if not isinstance(entry, dict):
                    continue
                event_type = entry.get("event_type")
                if event_type not in ("EXECUTION_REPORT", "PARTIAL_EXECUTION", "FILLED_EXECUTION"):
                    continue

                data = entry.get("data", {})
                exec_id = data.get("exec_id")
                if exec_id:
                    self._processed_exec_ids.add(str(exec_id))

                order_id_raw = data.get("order_id")
                client_id = data.get("client_order_id")
                cum_qty = int(data.get("cum_executed_qty", 0))
                status_str = data.get("status")

                if order_id_raw:
                    try:
                        order_id = uuid.UUID(str(order_id_raw))
                        self._executed_qty_history[order_id] = cum_qty
                        if status_str:
                            status_enum = OrderStatus(status_str)
                            self.fsm.states[order_id] = status_enum
                            if status_enum not in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED):
                                self._cum_executed_qty[order_id] = cum_qty
                            else:
                                self._cum_executed_qty.pop(order_id, None)
                                self._active_orders.pop(order_id, None)
                    except Exception as e:
                        logger.warning(f"[OrderRouter] Failed to recover order {order_id_raw}: {e}")

                if client_id:
                    self._client_to_executed_qty[str(client_id)] = cum_qty

                recovered_count += 1

            logger.info(f"[OrderRouter] Successfully recovered {recovered_count} execution events from WAL.")
            return recovered_count

    def is_execution_processed(self, exec_id: str) -> bool:
        """[8단계-5] exec_id 중복 처리 완료 여부 조회."""
        with self._lock:
            return exec_id in self._processed_exec_ids

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
        """미체결 지연 주문 실제 Broker cancel_order() 호출 및 CANCEL_REQUESTED 전이 (D-09)"""
        with self._lock:
            if order_id not in self._active_orders:
                return False

            command, sub_time = self._active_orders[order_id]
            client_order_id = getattr(command, "client_order_id", str(order_id))
            broker = broker_adapter or self._order_brokers.get(order_id)

            if broker is not None:
                try:
                    cancelled_req = broker.cancel_order(client_order_id)
                    if cancelled_req:
                        # [D-09] 취소 요청 성공 시 CANCEL_REQUESTED로 전이하며, 실제 취소 확정 전까지 active_orders 유지
                        self.fsm.transition_sync(order_id, OrderStatus.CANCEL_REQUESTED)
                        logger.info(
                            f"[OrderRouter] Stale order {order_id} ({client_order_id}) cancel requested to Broker (CANCEL_REQUESTED)."
                        )
                        return True
                    else:
                        logger.warning(
                            f"[OrderRouter] Broker failed to cancel stale order {order_id} ({client_order_id}). Order preserved."
                        )
                        return False
                except Exception as exc:
                    logger.error(
                        f"[OrderRouter] Exception while cancelling stale order {order_id} ({client_order_id}) via Broker: {exc}"
                    )
                    return False
            else:
                self.fsm.transition_sync(order_id, OrderStatus.CANCEL_REQUESTED)
                logger.info(f"[OrderRouter] Stale order {order_id} cancel requested (no broker attached).")
                return True

    def confirm_cancel(self, order_identifier: Any) -> bool:
        """[D-09] 실제 Broker 취소 확정(Cancellation Confirmation) 수신 시 CANCEL_REQUESTED -> CANCELLED 전이 및 active 주문 정리"""
        with self._lock:
            order_id: Optional[uuid.UUID] = None
            if isinstance(order_identifier, uuid.UUID):
                order_id = order_identifier
            elif isinstance(order_identifier, str):
                # client_order_id로부터 order_uuid 탐색
                for u, (cmd, _) in self._active_orders.items():
                    if getattr(cmd, "client_order_id", None) == order_identifier:
                        order_id = u
                        break

            if order_id is None:
                logger.warning(f"[OrderRouter] Cannot confirm cancellation for unknown order identifier: {order_identifier}")
                return False

            current_status = self.fsm.get_status(order_id)
            if current_status != OrderStatus.CANCEL_REQUESTED:
                logger.warning(
                    f"[OrderRouter] Cannot confirm cancellation for order {order_id}: "
                    f"Current status is {current_status}, expected {OrderStatus.CANCEL_REQUESTED}"
                )
                return False

            self.fsm.transition_sync(order_id, OrderStatus.CANCELLED)
            self._active_orders.pop(order_id, None)
            self._order_brokers.pop(order_id, None)
            self._cum_executed_qty.pop(order_id, None)
            logger.info(f"[OrderRouter] Order {order_id} ({order_identifier}) CANCELLED confirmed safely.")
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

    def reconcile_with_broker(self, broker_adapter: Any) -> Dict[str, Any]:
        """[D-12] 브로커의 공식 Recovery 조회 계약(get_open_orders, get_order_status)을 통해 활성 주문 상태 대사 및 안전 동기화"""
        with self._lock:
            reconcile_summary = {
                "active_orders_checked": len(self._active_orders),
                "open_orders_broker_count": 0,
                "confirmed_cancelled": 0,
                "synced_orders": 0,
            }
            if broker_adapter is None or not hasattr(broker_adapter, "get_open_orders"):
                return reconcile_summary

            try:
                open_orders = broker_adapter.get_open_orders()
                reconcile_summary["open_orders_broker_count"] = len(open_orders)
            except Exception as exc:
                logger.error(f"[OrderRouter] Failed to fetch open orders during broker reconcile: {exc}")
                return reconcile_summary

            broker_open_client_ids = {
                str(item.get("client_order_id", "")) for item in open_orders if isinstance(item, dict)
            }
            broker_open_ids = {
                str(item.get("broker_order_id", "")) for item in open_orders if isinstance(item, dict)
            }

            for order_id, (cmd, _) in list(self._active_orders.items()):
                client_id = getattr(cmd, "client_order_id", str(order_id))
                broker_order_id = self._order_to_broker_id.get(order_id) or ""
                current_status = self.fsm.get_status(order_id)

                is_open_in_broker = (client_id in broker_open_client_ids) or (
                    bool(broker_order_id) and broker_order_id in broker_open_ids
                )

                if not is_open_in_broker:
                    order_status_info = None
                    if hasattr(broker_adapter, "get_order_status"):
                        try:
                            order_status_info = broker_adapter.get_order_status(client_id)
                        except Exception as exc:
                            logger.warning(f"[OrderRouter] Failed to query order status for {client_id}: {exc}")

                    # 1. CANCEL_REQUESTED 상태에서 브로커 미체결에 없는 경우 (취소 확정 또는 체결 완료)
                    if current_status == OrderStatus.CANCEL_REQUESTED:
                        if order_status_info and order_status_info.get("status") == "FILLED":
                            self.fsm.transition_sync(order_id, OrderStatus.FILLED)
                            self._active_orders.pop(order_id, None)
                            self._order_brokers.pop(order_id, None)
                            self._cum_executed_qty.pop(order_id, None)
                            reconcile_summary["synced_orders"] += 1
                        elif order_status_info is None or order_status_info.get("status") == "CANCELLED":
                            self.confirm_cancel(order_id)
                            reconcile_summary["confirmed_cancelled"] += 1

                    # 2. SENT / ACCEPTED / PARTIAL 상태에서 브로커 체결이 완료(FILLED)된 경우 안전 동기화
                    elif order_status_info and order_status_info.get("status") == "FILLED":
                        if current_status in (OrderStatus.SENT, OrderStatus.ACCEPTED, OrderStatus.PARTIAL):
                            self.fsm.transition_sync(order_id, OrderStatus.FILLED)
                            self._active_orders.pop(order_id, None)
                            self._order_brokers.pop(order_id, None)
                            self._cum_executed_qty.pop(order_id, None)
                            reconcile_summary["synced_orders"] += 1

            return reconcile_summary

