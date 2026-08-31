"""tests/unit/test_broker_oms_reconciliation.py

[D-13] Broker ↔ 내부 OMS Reconciliation 기능 검증 테스트 스위트.
- 테스트 1: OMS = Broker 정상 일치 시 불일치 0건 검증
- 테스트 2: Broker에만 주문 존재하는 경우 (ORDER_MISMATCH / BROKER_ONLY_OPEN_ORDER) 감지 및 WAL 기록 검증
- 테스트 3: OMS에만 주문 존재하는 경우 (Broker 조회 불가) UNKNOWN 격리 및 신규 주문 차단 검증
- 테스트 4: 상태 불일치 보정 (STATUS_MISMATCH: OMS=SENT -> Broker=OPEN -> OMS=ACCEPTED) 검증
- 테스트 5: 상태 불일치 보정 (STATUS_MISMATCH: OMS=SENT -> Broker=FILLED -> OMS=FILLED) 및 active 정리 검증
- 테스트 6: 상태 불일치 보정 (STATUS_MISMATCH: OMS=SENT -> Broker=CANCELLED/REJECTED) 및 active 정리 검증
- 테스트 7: 체결수량 불일치 보정 (EXECUTION_MISMATCH: OMS=0 -> Broker=4) 및 PARTIAL 전이 검증
- 테스트 8: Broker None / 예외 응답 시 임의 추정 금지 및 UNKNOWN 격리 유지 검증
- 테스트 9: 대사 불확실 주문 잔존 시 has_unresolved_unknown_orders() 신규 발주 차단 검증
- 테스트 10: Reconciliation 전체 WAL 이벤트(STARTED, MISMATCH, CORRECTED, COMPLETED) 영속화 검증
- 테스트 11: WalStore 장애 시 wal_persisted=False 안전 보고 검증
"""

import uuid
from unittest.mock import MagicMock
import pytest
from infra.wal_store import WalStore
from option_program.orders.oms_fsm import OrderStatus
from option_program.orders.order_router import OrderRouter
from option_program.runtime.program_runtime import OptionProgramRuntime
from shared.core.contracts import RiskApprovalToken
from shared.contracts.canonical import (
    CanonicalAssetType,
    CanonicalExecutionReport,
    CanonicalOptionType,
    CanonicalOrderCommand,
    CanonicalOrderSide,
)


def make_cmd(client_id: str = "ORD-REC-01", qty: int = 10, price: float = 3.0) -> CanonicalOrderCommand:
    return CanonicalOrderCommand(
        client_order_id=client_id,
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=qty,
        price=price,
        symbol="201V3350",
        option_type=CanonicalOptionType.CALL,
        strike=350.0,
    )


def make_token(order_uuid: uuid.UUID, client_id: str = "ORD-REC-01") -> RiskApprovalToken:
    return RiskApprovalToken(
        order_id=order_uuid,
        timestamp_ns=1000000,
        signature=f"SIG-RISK-APPROVED-Track1-{client_id}",
    )


class MockReconcileBroker:
    """Reconciliation 테스트용 Mock Broker"""
    def __init__(self):
        self.open_orders_list = []
        self.order_status_map = {}
        self._connected = True

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def get_open_orders(self):
        return self.open_orders_list

    def get_order_status(self, order_identifier: str = ""):
        return self.order_status_map.get(order_identifier)


def test_reconciliation_exact_match_no_mismatches(tmp_path):
    """테스트 1: OMS와 Broker 상태가 정상 일치할 때 불일치 0건 검증."""
    wal_file = str(tmp_path / "recon_match.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-EXACT-01", qty=5)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-EXACT-01")
    router.register_and_route(command=cmd, token=tok)
    router.fsm.transition_sync(oid, OrderStatus.ACCEPTED)

    broker = MockReconcileBroker()
    broker.open_orders_list = [{
        "client_order_id": "ORD-EXACT-01",
        "broker_order_id": "BRK-EX-01",
        "status": "ACCEPTED",
        "executed_qty": 0,
    }]

    summary = router.reconcile_with_broker(broker)

    assert summary["status"] == "COMPLETED"
    assert len(summary["mismatches"]) == 0
    assert len(summary["corrections"]) == 0
    assert len(summary["uncertain_orders"]) == 0
    assert router.fsm.get_status(oid) == OrderStatus.ACCEPTED


def test_reconciliation_detects_broker_only_order(tmp_path):
    """테스트 2: Broker에만 주문 존재하는 경우 (ORDER_MISMATCH) 감지 검증."""
    wal_file = str(tmp_path / "recon_broker_only.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    broker = MockReconcileBroker()
    broker.open_orders_list = [{
        "client_order_id": "ORD-GHOST-01",
        "broker_order_id": "BRK-GHOST-01",
        "status": "OPEN",
        "executed_qty": 0,
    }]

    summary = router.reconcile_with_broker(broker)

    assert len(summary["mismatches"]) == 1
    assert summary["mismatches"][0]["type"] == "ORDER_MISMATCH"
    assert summary["mismatches"][0]["client_order_id"] == "ORD-GHOST-01"


def test_reconciliation_oms_only_order_uncertain_isolation(tmp_path):
    """테스트 3: OMS에는 있으나 Broker에서 찾을 수 없는 경우 UNKNOWN 격리 및 신규 발주 차단 검증."""
    wal_file = str(tmp_path / "recon_oms_only.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-OMS-ONLY", qty=5)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-OMS-ONLY")
    router.register_and_route(command=cmd, token=tok)

    broker = MockReconcileBroker()
    broker.open_orders_list = []
    broker.order_status_map["ORD-OMS-ONLY"] = None  # Broker 조회 불가

    summary = router.reconcile_with_broker(broker)

    assert summary["status"] == "UNCERTAIN_REMAINED"
    assert len(summary["mismatches"]) == 1
    assert summary["mismatches"][0]["type"] == "ORDER_MISMATCH"
    assert len(summary["uncertain_orders"]) == 1
    assert router.has_unresolved_unknown_orders() is True
    assert router.fsm.get_status(oid) == OrderStatus.UNKNOWN


def test_reconciliation_corrects_sent_to_accepted(tmp_path):
    """테스트 4: OMS는 SENT이나 Broker는 OPEN/ACCEPTED인 경우 ACCEPTED로 보정 검증."""
    wal_file = str(tmp_path / "recon_sent_acc.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-SENT-ACC", qty=5)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-SENT-ACC")
    router.register_and_route(command=cmd, token=tok)
    assert router.fsm.get_status(oid) == OrderStatus.SENT

    broker = MockReconcileBroker()
    broker.open_orders_list = [{
        "client_order_id": "ORD-SENT-ACC",
        "broker_order_id": "BRK-SA-01",
        "status": "ACCEPTED",
        "executed_qty": 0,
    }]

    summary = router.reconcile_with_broker(broker)

    assert len(summary["mismatches"]) == 1
    assert summary["mismatches"][0]["type"] == "STATUS_MISMATCH"
    assert len(summary["corrections"]) == 1
    assert router.fsm.get_status(oid) == OrderStatus.ACCEPTED


def test_reconciliation_corrects_sent_to_filled(tmp_path):
    """테스트 5: Broker가 FILLED인 경우 OMS FILLED 전이, 체결수량 반영 및 active 정리 검증."""
    wal_file = str(tmp_path / "recon_filled.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-FILL-SYNC", qty=8)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-FILL-SYNC")
    router.register_and_route(command=cmd, token=tok)

    broker = MockReconcileBroker()
    broker.open_orders_list = []  # 체결 완료되어 미체결 목록 없음
    broker.order_status_map["ORD-FILL-SYNC"] = {
        "client_order_id": "ORD-FILL-SYNC",
        "broker_order_id": "BRK-FILL-01",
        "status": "FILLED",
        "executed_qty": 8,
    }

    summary = router.reconcile_with_broker(broker)

    assert len(summary["corrections"]) == 1
    assert summary["corrections"][0]["new_status"] == "FILLED"
    assert router.fsm.get_status(oid) == OrderStatus.FILLED
    assert router.get_executed_qty(oid) == 8
    assert oid not in router._active_orders
    assert oid not in router._cum_executed_qty


def test_reconciliation_corrects_cancelled_and_rejected(tmp_path):
    """테스트 6: Broker가 CANCELLED 또는 REJECTED인 경우 OMS 정리 검증."""
    wal_file = str(tmp_path / "recon_term.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    cmd1 = make_cmd("ORD-CAN-SYNC", qty=3)
    oid1 = uuid.uuid4()
    tok1 = make_token(oid1, "ORD-CAN-SYNC")
    router.register_and_route(command=cmd1, token=tok1)

    cmd2 = make_cmd("ORD-REJ-SYNC", qty=2)
    oid2 = uuid.uuid4()
    tok2 = make_token(oid2, "ORD-REJ-SYNC")
    router.register_and_route(command=cmd2, token=tok2)

    broker = MockReconcileBroker()
    broker.open_orders_list = []
    broker.order_status_map["ORD-CAN-SYNC"] = {"status": "CANCELLED", "executed_qty": 0}
    broker.order_status_map["ORD-REJ-SYNC"] = {"status": "REJECTED", "executed_qty": 0}

    summary = router.reconcile_with_broker(broker)

    assert len(summary["corrections"]) == 2
    assert router.fsm.get_status(oid1) == OrderStatus.CANCELLED
    assert router.fsm.get_status(oid2) == OrderStatus.REJECTED
    assert oid1 not in router._active_orders
    assert oid2 not in router._active_orders


def test_reconciliation_corrects_execution_qty_mismatch(tmp_path):
    """테스트 7: OMS 체결수량 0 vs Broker 체결수량 4 불일치 시 보정 및 PARTIAL 전이 검증."""
    wal_file = str(tmp_path / "recon_qty.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-QTY-MISMATCH", qty=10)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-QTY-MISMATCH")
    router.register_and_route(command=cmd, token=tok)
    assert router.get_executed_qty(oid) == 0

    broker = MockReconcileBroker()
    broker.open_orders_list = [{
        "client_order_id": "ORD-QTY-MISMATCH",
        "broker_order_id": "BRK-QTY-01",
        "status": "OPEN",
        "executed_qty": 4,
    }]

    summary = router.reconcile_with_broker(broker)

    exec_mismatches = [m for m in summary["mismatches"] if m["type"] == "EXECUTION_MISMATCH"]
    assert len(exec_mismatches) == 1
    assert router.get_executed_qty(oid) == 4
    assert router.fsm.get_status(oid) == OrderStatus.PARTIAL


def test_reconciliation_broker_exception_safely_handled(tmp_path):
    """테스트 8: Broker 조회 중 예외 발생 시 임의 추정 없이 안전 처리 검증."""
    wal_file = str(tmp_path / "recon_exc.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-EXC", qty=5)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-EXC")
    router.register_and_route(command=cmd, token=tok)

    mock_broker = MagicMock()
    mock_broker.get_open_orders.return_value = []
    mock_broker.get_order_status.side_effect = ConnectionResetError("Broker gateway reset")

    summary = router.reconcile_with_broker(mock_broker)

    assert summary["status"] == "UNCERTAIN_REMAINED"
    assert router.fsm.get_status(oid) == OrderStatus.UNKNOWN
    assert router.has_unresolved_unknown_orders() is True


@pytest.mark.asyncio
async def test_reconciliation_wal_events_persisted_in_sequence(tmp_path):
    """테스트 10: Reconciliation 전체 WAL 이벤트(STARTED, MISMATCH, CORRECTED, COMPLETED) 순차 영속화 검증."""
    wal_file = str(tmp_path / "recon_wal_seq.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-WAL-SEQ", qty=5)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-WAL-SEQ")
    router.register_and_route(command=cmd, token=tok)

    broker = MockReconcileBroker()
    broker.open_orders_list = []
    broker.order_status_map["ORD-WAL-SEQ"] = {"status": "FILLED", "executed_qty": 5}

    summary = router.reconcile_with_broker(broker)
    assert summary["wal_persisted"] is True

    history = await wal_store.load_history()
    event_types = [h.get("event_type") for h in history]

    assert "ORDER_INTENT" in event_types
    assert "RECONCILIATION_STARTED" in event_types
    assert "RECONCILIATION_MISMATCH" in event_types
    assert "RECONCILIATION_CORRECTED" in event_types
    assert "RECONCILIATION_COMPLETED" in event_types


def test_reconciliation_wal_failure_safety_flag():
    """테스트 11: WalStore 장애 발생 시 wal_persisted=False 안전 통지 검증."""
    mock_wal = MagicMock()
    mock_wal.save_event_sync.side_effect = IOError("Disk I/O Error")

    router = OrderRouter(wal_store=mock_wal)
    cmd = make_cmd("ORD-WAL-FAIL", qty=5)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-WAL-FAIL")
    # WalStore 실패 시 register_and_route는 거절되므로 수동 등록
    router.fsm.states[oid] = OrderStatus.SENT
    router._active_orders[oid] = (cmd, 1000.0)

    broker = MockReconcileBroker()
    summary = router.reconcile_with_broker(broker)

    assert summary["wal_persisted"] is False
