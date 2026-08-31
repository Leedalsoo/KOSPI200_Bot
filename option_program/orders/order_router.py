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
    CanonicalOrderSide,
    CanonicalOptionType,
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
        self._client_to_order_id: Dict[str, uuid.UUID] = {}
        # [8단계-3] 주문별 실제 체결수량 권위 저장소 (미체결/부분체결/완료체결 전수 보존)
        self._executed_qty_history: Dict[uuid.UUID, int] = {}
        self._client_to_executed_qty: Dict[str, int] = {}
        # [8단계-5] Execution ID 중복수신 방어용 멱등성 저장소
        self._processed_exec_ids: Set[str] = set()
        # [D-16] 타임아웃 UNKNOWN 주문 격리 및 복구 저장소 (order_id -> (cmd, timestamp, reason))
        self._unknown_orders: Dict[uuid.UUID, Tuple[CanonicalOrderCommand, float, str]] = {}

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
            if getattr(command, "client_order_id", None):
                self._client_to_order_id[command.client_order_id] = order_id
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
    ) -> bool:
        """체결 보고서 수신에 따른 FSM 상태 전이 및 누적 체결 관리 (WAL 성공 선행 보장)"""
        with self._lock:
            # [8단계-5 / D-17] Execution ID 중복수신 방어 (멱등성 보장)
            exec_id = getattr(report, "exec_id", None)
            exec_id_str = str(exec_id) if exec_id is not None and str(exec_id).strip() != "" else None
            if exec_id_str:
                if exec_id_str in self._processed_exec_ids:
                    logger.warning(
                        f"[OrderRouter] Duplicate execution report ignored (Idempotency): "
                        f"exec_id={exec_id_str}, order_id={order_id}"
                    )
                    return True

            cmd_info = self._active_orders.get(order_id)
            requested_qty = cmd_info[0].qty if cmd_info else None
            client_id = cmd_info[0].client_order_id if cmd_info else getattr(report, "client_order_id", None)
            prev_cum = self._cum_executed_qty.get(order_id, 0)
            new_cum = prev_cum + report.executed_qty

            # 목표 상태 및 체결 유형 사전 판정
            if report.executed_qty > 0:
                if requested_qty is not None and new_cum > requested_qty:
                    target_status = OrderStatus.REJECTED
                    is_oversized = True
                elif requested_qty is not None and new_cum < requested_qty:
                    target_status = OrderStatus.PARTIAL
                    is_oversized = False
                elif requested_qty is not None and new_cum == requested_qty:
                    target_status = OrderStatus.FILLED
                    is_oversized = False
                else:
                    target_status = OrderStatus.REJECTED
                    is_oversized = False
            else:
                target_status = OrderStatus.REJECTED
                is_oversized = False

            # [D-17] WAL 영속화 선행 - WAL 저장 실패 시 메모리 체결 상태 변경 절대 금지
            wal_ok = self._persist_execution_wal(order_id, report, new_cum, requested_qty, target_status, client_id)
            if not wal_ok:
                logger.error(
                    f"[OrderRouter] WAL persistence failed for order {order_id} (Client: {client_id}, Exec: {exec_id_str}). "
                    f"Aborting execution state transition to maintain consistency."
                )
                return False

            # WAL 영속화 성공 후 멱등성 exec_id 및 메모리 체결 상태 반영
            if exec_id_str:
                self._processed_exec_ids.add(exec_id_str)

            if target_status == OrderStatus.PARTIAL:
                self._cum_executed_qty[order_id] = new_cum
                self._executed_qty_history[order_id] = new_cum
                if client_id:
                    self._client_to_executed_qty[client_id] = new_cum
                self.fsm.transition_sync(order_id, OrderStatus.PARTIAL)
                logger.info(
                    f"[OrderRouter] Order {order_id} PARTIAL: {new_cum}/{requested_qty}@{report.executed_price}"
                )
            elif target_status == OrderStatus.FILLED:
                self._cum_executed_qty[order_id] = new_cum
                self._executed_qty_history[order_id] = new_cum
                if client_id:
                    self._client_to_executed_qty[client_id] = new_cum
                self.fsm.transition_sync(order_id, OrderStatus.FILLED)
                self._active_orders.pop(order_id, None)
                self._order_brokers.pop(order_id, None)
                self._cum_executed_qty.pop(order_id, None)
                logger.info(f"[OrderRouter] Order {order_id} FILLED: {new_cum}@{report.executed_price}")
            else:  # REJECTED
                self.fsm.transition_sync(order_id, OrderStatus.REJECTED)
                self._active_orders.pop(order_id, None)
                self._order_brokers.pop(order_id, None)
                self._cum_executed_qty.pop(order_id, None)
                if is_oversized:
                    logger.error(
                        f"[OrderRouter] Order {order_id} oversized execution rejected: "
                        f"cumulative_qty={new_cum} > requested_qty={requested_qty}"
                    )
                elif report.executed_qty <= 0:
                    logger.warning(f"[OrderRouter] Order {order_id} REJECTED by Broker.")
                else:
                    logger.warning(
                        f"[OrderRouter] Order {order_id} received execution report for inactive/unknown order: REJECTED."
                    )
            return True

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
    ) -> bool:
        """[D-10 / D-17] 체결 이벤트 및 누적 체결 상태를 WAL 영속 저장소에 즉시 기록"""
        if self.wal_store is None:
            return True

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
                "executed_price": float(getattr(report, "executed_price", 0.0) or 0.0),
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
            return True
        except Exception as exc:
            logger.error(f"[OrderRouter] Failed to persist execution to WAL: {exc}")
            return False

    def recover_from_wal(self, events: List[Dict[str, Any]]) -> int:
        """[D-10 / D-13 / D-17] WAL 이벤트 로그로부터 주문 의도, UNKNOWN 상태, 누적 체결, 멱등성 exec_id, FSM 상태 복원"""
        with self._lock:
            recovered_count = 0
            for entry in events:
                if not isinstance(entry, dict):
                    continue
                event_type = entry.get("event_type")
                data = entry.get("data", {})
                if not isinstance(data, dict):
                    continue

                order_id_raw = data.get("order_id")
                client_id = data.get("client_order_id")
                order_id: Optional[uuid.UUID] = None
                if order_id_raw:
                    try:
                        order_id = uuid.UUID(str(order_id_raw))
                    except Exception:
                        order_id = None

                # 1. ORDER_INTENT 복원
                if event_type == "ORDER_INTENT":
                    if order_id:
                        try:
                            side_str = data.get("side", "BUY")
                            side_enum = CanonicalOrderSide.BUY if side_str == "BUY" else CanonicalOrderSide.SELL
                            opt_str = data.get("option_type")
                            opt_enum = CanonicalOptionType(opt_str) if opt_str in ("CALL", "PUT") else None
                            cmd = CanonicalOrderCommand(
                                client_order_id=str(client_id) if client_id else str(order_id),
                                track_id=str(data.get("track_id", "Track1")),
                                asset_type=CanonicalAssetType.OPTION,
                                side=side_enum,
                                qty=int(data.get("qty", 0)),
                                price=float(data.get("price", 0.0)),
                                symbol=str(data.get("symbol", "KOSPI200")),
                                option_type=opt_enum,
                                strike=float(data.get("strike", 0.0)),
                            )
                            ts = float(data.get("timestamp", time.time()) or time.time())
                            self._active_orders[order_id] = (cmd, ts)
                            self.fsm.states[order_id] = OrderStatus.SENT
                            if client_id:
                                self._client_to_order_id[str(client_id)] = order_id
                            recovered_count += 1
                        except Exception as exc:
                            logger.warning(f"[OrderRouter] Failed to recover ORDER_INTENT {order_id_raw}: {exc}")

                # 2. BROKER_SEND_STARTED 복원
                elif event_type == "BROKER_SEND_STARTED":
                    if order_id and order_id in self.fsm.states:
                        self.fsm.states[order_id] = OrderStatus.SENT
                    recovered_count += 1

                # 3. BROKER_UNKNOWN 복원
                elif event_type == "BROKER_UNKNOWN":
                    if order_id:
                        self.fsm.states[order_id] = OrderStatus.UNKNOWN
                        cmd_info = self._active_orders.get(order_id)
                        cmd = cmd_info[0] if cmd_info else CanonicalOrderCommand(
                            client_order_id=str(client_id) if client_id else str(order_id),
                            track_id=str(data.get("track_id", "Track1")),
                            asset_type=CanonicalAssetType.OPTION,
                            side=CanonicalOrderSide.BUY,
                            qty=int(data.get("qty", 0)),
                            price=float(data.get("price", 0.0)),
                        )
                        ts = float(data.get("timestamp", time.time()) or time.time())
                        reason = str(data.get("reason", "TIMEOUT_UNKNOWN"))
                        self._unknown_orders[order_id] = (cmd, ts, reason)
                        recovered_count += 1

                # 4. UNKNOWN_RECOVERED 복원
                elif event_type == "UNKNOWN_RECOVERED":
                    if order_id:
                        self._unknown_orders.pop(order_id, None)
                        rec_status_str = data.get("recovered_status")
                        if rec_status_str:
                            try:
                                status_enum = OrderStatus(rec_status_str)
                                self.fsm.states[order_id] = status_enum
                                if status_enum in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED):
                                    self._cum_executed_qty.pop(order_id, None)
                                    self._active_orders.pop(order_id, None)
                            except Exception as exc:
                                logger.warning(f"[OrderRouter] Invalid recovered_status {rec_status_str}: {exc}")
                        recovered_count += 1

                # 5. 체결 이벤트 복원 (EXECUTION_REPORT, PARTIAL_EXECUTION, FILLED_EXECUTION)
                elif event_type in ("EXECUTION_REPORT", "PARTIAL_EXECUTION", "FILLED_EXECUTION"):
                    exec_id = data.get("exec_id")
                    if exec_id:
                        self._processed_exec_ids.add(str(exec_id))

                    cum_qty = int(data.get("cum_executed_qty", 0))
                    status_str = data.get("status")

                    if order_id:
                        try:
                            self._executed_qty_history[order_id] = cum_qty
                            if status_str:
                                status_enum = OrderStatus(status_str)
                                self.fsm.states[order_id] = status_enum
                                if status_enum not in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED):
                                    self._cum_executed_qty[order_id] = cum_qty
                                else:
                                    self._cum_executed_qty.pop(order_id, None)
                                    self._active_orders.pop(order_id, None)
                                    self._unknown_orders.pop(order_id, None)
                        except Exception as e:
                            logger.warning(f"[OrderRouter] Failed to recover execution order {order_id_raw}: {e}")

                    if client_id:
                        self._client_to_executed_qty[str(client_id)] = cum_qty

                    recovered_count += 1

            logger.info(f"[OrderRouter] Successfully recovered {recovered_count} events from WAL.")
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

    def _persist_reconciliation_wal(self, event_type: str, data: Dict[str, Any]) -> bool:
        """Reconciliation WAL 이벤트 기록 헬퍼"""
        if self.wal_store is None:
            return True
        try:
            if hasattr(self.wal_store, "save_event_sync"):
                self.wal_store.save_event_sync(event_type, data)
            return True
        except Exception as exc:
            logger.error(f"[OrderRouter] Failed to persist {event_type} to WAL: {exc}")
            return False

    def reconcile_with_broker(self, broker_adapter: Any) -> Dict[str, Any]:
        """[D-13] Broker 실제 주문 상태와 내부 OMS 간의 종합 Reconciliation (대사, 불일치 감지, 확정 상태 보정, WAL 영속화)"""
        with self._lock:
            recon_id = f"RECON-{uuid.uuid4().hex[:8]}"
            start_time = time.time()
            mismatches: List[Dict[str, Any]] = []
            corrections: List[Dict[str, Any]] = []
            uncertain_orders: List[Dict[str, Any]] = []

            summary: Dict[str, Any] = {
                "reconciliation_id": recon_id,
                "started_at": start_time,
                "completed_at": 0.0,
                "active_orders_checked": len(self._active_orders),
                "broker_open_orders_count": 0,
                "open_orders_broker_count": 0,
                "confirmed_cancelled": 0,
                "synced_orders": 0,
                "recovered": 0,
                "remained_unknown": 0,
                "mismatches": mismatches,
                "corrections": corrections,
                "uncertain_orders": uncertain_orders,
                "status": "COMPLETED",
                "wal_persisted": True,
            }

            wal_ok = self._persist_reconciliation_wal(
                "RECONCILIATION_STARTED",
                {
                    "reconciliation_id": recon_id,
                    "active_orders_count": len(self._active_orders),
                    "timestamp": str(start_time),
                },
            )
            if not wal_ok:
                summary["wal_persisted"] = False

            if broker_adapter is None:
                summary["status"] = "FAILED"
                summary["completed_at"] = time.time()
                return summary

            # 1. Broker Open Orders 조회
            open_orders: List[Any] = []
            if hasattr(broker_adapter, "get_open_orders"):
                try:
                    raw_open = broker_adapter.get_open_orders()
                    if isinstance(raw_open, list):
                        open_orders = raw_open
                    summary["broker_open_orders_count"] = len(open_orders)
                    summary["open_orders_broker_count"] = len(open_orders)
                except Exception as exc:
                    logger.error(f"[OrderRouter] Failed to fetch open orders from broker during reconcile: {exc}")
                    summary["status"] = "FAILED"
                    summary["completed_at"] = time.time()
                    return summary

            broker_open_by_client: Dict[str, Dict[str, Any]] = {}
            broker_open_by_broker_id: Dict[str, Dict[str, Any]] = {}
            for item in open_orders:
                if isinstance(item, dict):
                    cid = str(item.get("client_order_id", "")).strip()
                    bid = str(item.get("broker_order_id", "")).strip()
                    if cid:
                        broker_open_by_client[cid] = item
                    if bid:
                        broker_open_by_broker_id[bid] = item

            # 2. 내부 활성 주문 대사 순회
            for order_id, (cmd, sub_time) in list(self._active_orders.items()):
                client_id = getattr(cmd, "client_order_id", str(order_id))
                broker_order_id = self._order_to_broker_id.get(order_id) or self._client_to_broker_id.get(client_id, "")
                current_status = self.fsm.get_status(order_id)
                oms_cum_qty = self.get_executed_qty(order_id)

                # Case A: Broker Open Orders 목록에 존재하는 경우
                broker_info = broker_open_by_client.get(client_id) or (
                    broker_open_by_broker_id.get(broker_order_id) if broker_order_id else None
                )

                if broker_info is not None:
                    # 상태 비교
                    b_status_raw = broker_info.get("status", "OPEN")
                    b_qty = int(broker_info.get("executed_qty", 0))

                    # 1) 상태 불일치 (STATUS_MISMATCH: Broker가 명시적으로 ACCEPTED를 보고한 경우)
                    if current_status == OrderStatus.SENT and str(b_status_raw).upper() == "ACCEPTED":
                        mismatch_entry = {
                            "type": "STATUS_MISMATCH",
                            "order_id": str(order_id),
                            "client_order_id": client_id,
                            "oms_status": current_status.value if current_status else "NONE",
                            "broker_status": "ACCEPTED",
                        }
                        mismatches.append(mismatch_entry)
                        self._persist_reconciliation_wal("RECONCILIATION_MISMATCH", mismatch_entry)

                        # 확정 보정
                        self.fsm.transition_sync(order_id, OrderStatus.ACCEPTED)
                        corr_entry = {
                            "order_id": str(order_id),
                            "client_order_id": client_id,
                            "prev_status": current_status.value if current_status else "NONE",
                            "new_status": OrderStatus.ACCEPTED.value,
                        }
                        corrections.append(corr_entry)
                        self._persist_reconciliation_wal("RECONCILIATION_CORRECTED", corr_entry)

                    # 2) 체결 수량 불일치 (EXECUTION_MISMATCH)
                    if b_qty != oms_cum_qty:
                        exec_mismatch = {
                            "type": "EXECUTION_MISMATCH",
                            "order_id": str(order_id),
                            "client_order_id": client_id,
                            "oms_executed_qty": oms_cum_qty,
                            "broker_executed_qty": b_qty,
                        }
                        mismatches.append(exec_mismatch)
                        self._persist_reconciliation_wal("RECONCILIATION_MISMATCH", exec_mismatch)

                        # 확정 보정 (Broker 체결수량 반영)
                        self._cum_executed_qty[order_id] = b_qty
                        self._executed_qty_history[order_id] = b_qty
                        self._client_to_executed_qty[client_id] = b_qty
                        if b_qty > 0 and self.fsm.get_status(order_id) not in (OrderStatus.PARTIAL, OrderStatus.FILLED):
                            self.fsm.transition_sync(order_id, OrderStatus.PARTIAL)

                        corr_entry = {
                            "order_id": str(order_id),
                            "client_order_id": client_id,
                            "prev_executed_qty": oms_cum_qty,
                            "new_executed_qty": b_qty,
                        }
                        corrections.append(corr_entry)
                        self._persist_reconciliation_wal("RECONCILIATION_CORRECTED", corr_entry)

                # Case B: Broker Open Orders 목록에 없는 경우 -> get_order_status로 종결 상태 확인
                else:
                    target_id = broker_order_id if broker_order_id else client_id
                    status_info: Optional[Dict[str, Any]] = None
                    if hasattr(broker_adapter, "get_order_status"):
                        try:
                            status_info = broker_adapter.get_order_status(target_id)
                        except Exception as exc:
                            logger.warning(f"[OrderRouter] Exception querying get_order_status for {target_id}: {exc}")
                            status_info = None

                    # 조회 실패 / None / 불명확 -> 불확실 불일치로 안전 격리 (임의 추정 금지)
                    if status_info is None or not isinstance(status_info, dict):
                        mismatch_entry = {
                            "type": "ORDER_MISMATCH",
                            "subtype": "NOT_FOUND_IN_BROKER_OPEN_AND_STATUS_UNCERTAIN",
                            "order_id": str(order_id),
                            "client_order_id": client_id,
                            "oms_status": current_status.value if current_status else "NONE",
                        }
                        mismatches.append(mismatch_entry)
                        self._persist_reconciliation_wal("RECONCILIATION_MISMATCH", mismatch_entry)

                        # UNKNOWN으로 격리하여 신규 주문 안전 차단 발동
                        self.mark_order_unknown(order_id, reason="RECONCILIATION_UNCERTAIN")
                        uncertain_orders.append({
                            "order_id": str(order_id),
                            "client_order_id": client_id,
                            "reason": "NOT_FOUND_IN_BROKER_STATUS_UNCERTAIN",
                        })
                        continue

                    # 정상 확정 응답 수신 시 보정
                    b_status = str(status_info.get("status", "")).upper()
                    b_qty = int(status_info.get("executed_qty", 0))

                    # 1) Broker FILLED 확정
                    if b_status == "FILLED":
                        mismatch_entry = {
                            "type": "STATUS_MISMATCH",
                            "order_id": str(order_id),
                            "client_order_id": client_id,
                            "oms_status": current_status.value if current_status else "NONE",
                            "broker_status": "FILLED",
                        }
                        mismatches.append(mismatch_entry)
                        self._persist_reconciliation_wal("RECONCILIATION_MISMATCH", mismatch_entry)

                        # 상태 및 수량 보정 후 active 정리
                        self.fsm.transition_sync(order_id, OrderStatus.FILLED)
                        req_qty = getattr(cmd, "qty", b_qty)
                        final_qty = b_qty if b_qty > 0 else req_qty
                        self._executed_qty_history[order_id] = final_qty
                        self._client_to_executed_qty[client_id] = final_qty
                        self._active_orders.pop(order_id, None)
                        self._order_brokers.pop(order_id, None)
                        self._cum_executed_qty.pop(order_id, None)

                        corr_entry = {
                            "order_id": str(order_id),
                            "client_order_id": client_id,
                            "prev_status": current_status.value if current_status else "NONE",
                            "new_status": OrderStatus.FILLED.value,
                            "executed_qty": final_qty,
                        }
                        corrections.append(corr_entry)
                        summary["synced_orders"] += 1
                        self._persist_reconciliation_wal("RECONCILIATION_CORRECTED", corr_entry)

                    # 2) Broker CANCELLED 확정
                    elif b_status == "CANCELLED":
                        mismatch_entry = {
                            "type": "STATUS_MISMATCH",
                            "order_id": str(order_id),
                            "client_order_id": client_id,
                            "oms_status": current_status.value if current_status else "NONE",
                            "broker_status": "CANCELLED",
                        }
                        mismatches.append(mismatch_entry)
                        self._persist_reconciliation_wal("RECONCILIATION_MISMATCH", mismatch_entry)

                        if current_status == OrderStatus.CANCEL_REQUESTED:
                            self.confirm_cancel(order_id)
                        else:
                            self.fsm.transition_sync(order_id, OrderStatus.CANCEL_REQUESTED)
                            self.fsm.transition_sync(order_id, OrderStatus.CANCELLED)
                            self._active_orders.pop(order_id, None)
                            self._order_brokers.pop(order_id, None)
                            self._cum_executed_qty.pop(order_id, None)

                        corr_entry = {
                            "order_id": str(order_id),
                            "client_order_id": client_id,
                            "prev_status": current_status.value if current_status else "NONE",
                            "new_status": OrderStatus.CANCELLED.value,
                        }
                        corrections.append(corr_entry)
                        summary["confirmed_cancelled"] += 1
                        summary["synced_orders"] += 1
                        self._persist_reconciliation_wal("RECONCILIATION_CORRECTED", corr_entry)

                    # 3) Broker REJECTED 확정
                    elif b_status == "REJECTED":
                        mismatch_entry = {
                            "type": "STATUS_MISMATCH",
                            "order_id": str(order_id),
                            "client_order_id": client_id,
                            "oms_status": current_status.value if current_status else "NONE",
                            "broker_status": "REJECTED",
                        }
                        mismatches.append(mismatch_entry)
                        self._persist_reconciliation_wal("RECONCILIATION_MISMATCH", mismatch_entry)

                        self.fsm.transition_sync(order_id, OrderStatus.REJECTED)
                        self._active_orders.pop(order_id, None)
                        self._order_brokers.pop(order_id, None)
                        self._cum_executed_qty.pop(order_id, None)

                        corr_entry = {
                            "order_id": str(order_id),
                            "client_order_id": client_id,
                            "prev_status": current_status.value if current_status else "NONE",
                            "new_status": OrderStatus.REJECTED.value,
                        }
                        corrections.append(corr_entry)
                        summary["synced_orders"] += 1
                        self._persist_reconciliation_wal("RECONCILIATION_CORRECTED", corr_entry)

                    else:
                        # 알 수 없는 기타 응답 상태 -> 안전 격리
                        self.mark_order_unknown(order_id, reason=f"BROKER_UNEXPECTED_STATUS_{b_status}")
                        uncertain_orders.append({
                            "order_id": str(order_id),
                            "client_order_id": client_id,
                            "reason": f"UNEXPECTED_STATUS_{b_status}",
                        })

            # 3. Broker에만 열려있고 OMS에는 없는 주문 감지 (ORDER_MISMATCH)
            active_client_ids = {
                getattr(cmd, "client_order_id", str(u)) for u, (cmd, _) in self._active_orders.items()
            }
            for item in open_orders:
                if isinstance(item, dict):
                    cid = str(item.get("client_order_id", "")).strip()
                    bid = str(item.get("broker_order_id", "")).strip()
                    if cid and cid not in active_client_ids and cid not in self._client_to_order_id:
                        broker_only_mismatch = {
                            "type": "ORDER_MISMATCH",
                            "subtype": "BROKER_ONLY_OPEN_ORDER",
                            "client_order_id": cid,
                            "broker_order_id": bid,
                            "broker_status": item.get("status", "OPEN"),
                            "broker_executed_qty": item.get("executed_qty", 0),
                        }
                        mismatches.append(broker_only_mismatch)
                        self._persist_reconciliation_wal("RECONCILIATION_MISMATCH", broker_only_mismatch)
                        logger.warning(
                            f"[OrderRouter] Detected Broker-only open order (Client: {cid}, BrokerID: {bid})"
                        )

            # 4. UNKNOWN 주문 복구도 동시 연계
            if self._unknown_orders:
                unk_res = self.recover_unknown_orders(broker_adapter)
                summary["unknown_recovery_summary"] = unk_res
                summary["recovered"] = unk_res.get("recovered", 0)
                summary["remained_unknown"] = unk_res.get("remained_unknown", 0)

            end_time = time.time()
            summary["completed_at"] = end_time
            if uncertain_orders or self.has_unresolved_unknown_orders():
                summary["status"] = "UNCERTAIN_REMAINED"

            comp_wal_ok = self._persist_reconciliation_wal(
                "RECONCILIATION_COMPLETED",
                {
                    "reconciliation_id": recon_id,
                    "mismatches_count": len(mismatches),
                    "corrections_count": len(corrections),
                    "uncertain_count": len(uncertain_orders),
                    "status": summary["status"],
                    "timestamp": str(end_time),
                },
            )
            if not comp_wal_ok:
                summary["wal_persisted"] = False

            logger.info(
                f"[OrderRouter] Reconciliation {recon_id} completed (Mismatches: {len(mismatches)}, "
                f"Corrections: {len(corrections)}, Uncertain: {len(uncertain_orders)}, Status: {summary['status']})"
            )
            return summary

    def mark_order_unknown(self, order_identifier: Any, reason: str = "TIMEOUT_UNKNOWN") -> bool:
        """[D-16] Broker 타임아웃 주문을 UNKNOWN 상태로 전환 및 BROKER_UNKNOWN WAL 영속화"""
        with self._lock:
            order_id = order_identifier if isinstance(order_identifier, uuid.UUID) else self.get_order_uuid_by_client_id(str(order_identifier))
            if order_id is None:
                for u, (c, _) in self._active_orders.items():
                    if getattr(c, "client_order_id", None) == str(order_identifier):
                        order_id = u
                        break

            cmd_info = self._active_orders.get(order_id) if order_id else None
            cmd = cmd_info[0] if cmd_info else None
            client_id = getattr(cmd, "client_order_id", str(order_identifier))

            if order_id:
                self.fsm.transition_sync(order_id, OrderStatus.UNKNOWN)
                if cmd:
                    self._unknown_orders[order_id] = (cmd, time.time(), reason)
                else:
                    dummy_cmd = CanonicalOrderCommand(
                        client_order_id=client_id,
                        track_id="UNKNOWN",
                        asset_type=CanonicalAssetType.OPTION,
                        side=CanonicalOrderSide.BUY,
                        qty=0,
                        price=0.0,
                        symbol="UNKNOWN",
                    )
                    self._unknown_orders[order_id] = (dummy_cmd, time.time(), reason)

            # BROKER_UNKNOWN WAL 영속화
            if self.wal_store is not None:
                try:
                    side_val = getattr(cmd, "side", CanonicalOrderSide.BUY) if cmd else "BUY"
                    side_str = side_val.value if hasattr(side_val, "value") else str(side_val)
                    event_data = {
                        "order_id": str(order_id) if order_id else None,
                        "client_order_id": client_id,
                        "track_id": getattr(cmd, "track_id", "") if cmd else "",
                        "symbol": getattr(cmd, "symbol", "") if cmd else "",
                        "side": side_str,
                        "qty": getattr(cmd, "qty", 0) if cmd else 0,
                        "price": float(getattr(cmd, "price", 0.0) or 0.0) if cmd else 0.0,
                        "reason": reason,
                        "status": OrderStatus.UNKNOWN.value,
                        "timestamp": str(time.time()),
                    }
                    if hasattr(self.wal_store, "save_event_sync"):
                        self.wal_store.save_event_sync("BROKER_UNKNOWN", event_data)
                except Exception as exc:
                    logger.error(f"[OrderRouter] Failed to persist BROKER_UNKNOWN to WAL: {exc}")

            logger.warning(f"[OrderRouter] Order {client_id} (UUID: {order_id}) marked as UNKNOWN (Reason: {reason})")
            return True

    def has_unresolved_unknown_orders(self) -> bool:
        """[D-16] 미해결 UNKNOWN 상태의 주문이 남아있는지 확인"""
        with self._lock:
            return len(self._unknown_orders) > 0

    def recover_unknown_orders(self, broker_adapter: Any) -> Dict[str, Any]:
        """[D-16] UNKNOWN 주문에 대해 Broker 조회(get_order_status / get_open_orders)를 통한 확정 상태 복구 및 WAL 영속화"""
        with self._lock:
            summary = {
                "unknown_checked": len(self._unknown_orders),
                "recovered": 0,
                "remained_unknown": 0,
            }
            if not self._unknown_orders:
                return summary

            if broker_adapter is None:
                summary["remained_unknown"] = len(self._unknown_orders)
                return summary

            for order_id, (cmd, ts, reason) in list(self._unknown_orders.items()):
                client_id = getattr(cmd, "client_order_id", str(order_id))
                broker_order_id = self._order_to_broker_id.get(order_id) or self._client_to_broker_id.get(client_id)

                status_resp = None
                if hasattr(broker_adapter, "get_order_status"):
                    try:
                        target_id = broker_order_id if broker_order_id else client_id
                        status_resp = broker_adapter.get_order_status(target_id)
                    except Exception as exc:
                        logger.warning(f"[OrderRouter] Exception querying get_order_status for {client_id}: {exc}")

                # 보조 조회: get_open_orders
                if status_resp is None and hasattr(broker_adapter, "get_open_orders"):
                    try:
                        open_orders = broker_adapter.get_open_orders()
                        for item in open_orders:
                            if isinstance(item, dict) and (item.get("client_order_id") == client_id or (broker_order_id and item.get("broker_order_id") == broker_order_id)):
                                status_resp = item
                                break
                    except Exception as exc:
                        logger.warning(f"[OrderRouter] Exception querying get_open_orders for {client_id}: {exc}")

                # 조회 실패 또는 결과가 불명확한 경우 -> UNKNOWN 유지!
                if status_resp is None or not isinstance(status_resp, dict):
                    summary["remained_unknown"] += 1
                    continue

                b_status = status_resp.get("status")
                if not b_status:
                    summary["remained_unknown"] += 1
                    continue

                # status 문자열 정규화
                status_str = b_status.value if hasattr(b_status, "value") else str(b_status).upper()
                recovered_status: Optional[OrderStatus] = None
                b_exec_qty = int(status_resp.get("executed_qty", 0))

                if status_str in ("OPEN", "ACCEPTED", "PENDING", "SENT"):
                    recovered_status = OrderStatus.ACCEPTED
                    self.fsm.transition_sync(order_id, OrderStatus.ACCEPTED)
                    self._unknown_orders.pop(order_id, None)
                    summary["recovered"] += 1

                elif status_str == "PARTIAL":
                    recovered_status = OrderStatus.PARTIAL
                    self.fsm.transition_sync(order_id, OrderStatus.PARTIAL)
                    self._cum_executed_qty[order_id] = b_exec_qty
                    self._unknown_orders.pop(order_id, None)
                    summary["recovered"] += 1

                elif status_str == "FILLED":
                    recovered_status = OrderStatus.FILLED
                    self.fsm.transition_sync(order_id, OrderStatus.FILLED)
                    self._cum_executed_qty[order_id] = getattr(cmd, "qty", b_exec_qty)
                    self._active_orders.pop(order_id, None)
                    self._order_brokers.pop(order_id, None)
                    self._unknown_orders.pop(order_id, None)
                    summary["recovered"] += 1

                elif status_str == "CANCELLED":
                    recovered_status = OrderStatus.CANCELLED
                    self.fsm.transition_sync(order_id, OrderStatus.CANCELLED)
                    self._active_orders.pop(order_id, None)
                    self._order_brokers.pop(order_id, None)
                    self._unknown_orders.pop(order_id, None)
                    summary["recovered"] += 1

                elif status_str == "REJECTED":
                    recovered_status = OrderStatus.REJECTED
                    self.fsm.transition_sync(order_id, OrderStatus.REJECTED)
                    self._active_orders.pop(order_id, None)
                    self._order_brokers.pop(order_id, None)
                    self._unknown_orders.pop(order_id, None)
                    summary["recovered"] += 1

                else:
                    # 지원되지 않는 불명확 상태 -> UNKNOWN 유지
                    summary["remained_unknown"] += 1
                    continue

                # WAL UNKNOWN_RECOVERED 영속화
                if self.wal_store is not None and recovered_status is not None:
                    try:
                        rec_event_data = {
                            "order_id": str(order_id),
                            "client_order_id": client_id,
                            "broker_status": status_str,
                            "recovered_status": recovered_status.value,
                            "executed_qty": b_exec_qty,
                            "timestamp": str(time.time()),
                        }
                        if hasattr(self.wal_store, "save_event_sync"):
                            self.wal_store.save_event_sync("UNKNOWN_RECOVERED", rec_event_data)
                    except Exception as exc:
                        logger.error(f"[OrderRouter] Failed to persist UNKNOWN_RECOVERED to WAL: {exc}")

                logger.info(f"[OrderRouter] UNKNOWN order {client_id} successfully recovered to {recovered_status.value}")

            return summary

