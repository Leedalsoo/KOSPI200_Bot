"""tests/unit/test_unknown_order_timeout_recovery.py

[D-16] UNKNOWN 주문 상태 및 Timeout Recovery 검증 테스트 스위트.
- 테스트 1: OrderStatus.UNKNOWN 존재 및 SENT -> UNKNOWN 전이 검증
- 테스트 2: mark_order_unknown() 호출 시 BROKER_UNKNOWN 이벤트 WAL 영속화 검증
- 테스트 3: Broker OPEN/ACCEPTED 확정 결과 복구 및 UNKNOWN_RECOVERED WAL 기록 검증
- 테스트 4: Broker PARTIAL 확정 결과 복구 및 누적체결수량 보존 검증
- 테스트 5: Broker FILLED/CANCELLED/REJECTED 종료 확정 상태 복구 및 정리 검증
- 테스트 6: Broker 조회가 None/예외/불명확 시 UNKNOWN 상태 안전 유지 검증
- 테스트 7: UNKNOWN 미해결 주문 잔존 시 신규 주문 발주 안전 차단 검증
- 테스트 8: recover_unknown_orders() 반복 실행의 멱등성 검증
"""

import uuid
import pytest
from infra.wal_store import WalStore
from option_program.orders.oms_fsm import OmsFsm, OrderStatus
from option_program.orders.order_router import OrderRouter
from option_program.runtime.program_runtime import OptionProgramRuntime
from shared.core.contracts import RiskApprovalToken
from shared.contracts.canonical import (
    CanonicalAssetType,
    CanonicalOptionType,
    CanonicalOrderCommand,
    CanonicalOrderSide,
)


def make_cmd(client_id: str = "ORD-D16-01", qty: int = 5, price: float = 3.2) -> CanonicalOrderCommand:
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


def make_token(order_uuid: uuid.UUID, client_id: str = "ORD-D16-01") -> RiskApprovalToken:
    return RiskApprovalToken(
        order_id=order_uuid,
        timestamp_ns=1000000,
        signature=f"SIG-RISK-APPROVED-Track1-{client_id}",
    )


class MockBrokerAdapter:
    """테스트용 Broker Adapter"""
    def __init__(self):
        self.status_map = {}
        self.open_orders_list = []
        self.query_count = 0

    def get_order_status(self, order_identifier: str = ""):
        self.query_count += 1
        return self.status_map.get(order_identifier)

    def get_open_orders(self):
        return self.open_orders_list


def test_order_status_unknown_and_fsm_transition():
    """테스트 1: OrderStatus.UNKNOWN 존재 및 SENT -> UNKNOWN -> ACCEPTED 전이 무결성 검증."""
    assert hasattr(OrderStatus, "UNKNOWN")
    assert OrderStatus.UNKNOWN.value == "UNKNOWN"

    fsm = OmsFsm()
    oid = uuid.uuid4()
    fsm.transition_sync(oid, OrderStatus.NEW)
    fsm.transition_sync(oid, OrderStatus.VALIDATED)
    fsm.transition_sync(oid, OrderStatus.SENT)

    # SENT -> UNKNOWN 전이
    assert fsm.transition_sync(oid, OrderStatus.UNKNOWN) is True
    assert fsm.get_status(oid) == OrderStatus.UNKNOWN

    # UNKNOWN -> ACCEPTED 복구 전이
    assert fsm.transition_sync(oid, OrderStatus.ACCEPTED) is True
    assert fsm.get_status(oid) == OrderStatus.ACCEPTED


@pytest.mark.asyncio
async def test_mark_order_unknown_persists_broker_unknown_wal(tmp_path):
    """테스트 2: mark_order_unknown() 시 BROKER_UNKNOWN 이벤트가 WAL에 영속화되는지 검증."""
    wal_file = str(tmp_path / "unknown.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-UNK-01", qty=10, price=3.5)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-UNK-01")
    router.register_and_route(command=cmd, token=tok)

    # 타임아웃 발생 -> UNKNOWN 전환
    router.mark_order_unknown("ORD-UNK-01", reason="TIMEOUT_UNKNOWN")

    assert router.fsm.get_status(oid) == OrderStatus.UNKNOWN
    assert router.has_unresolved_unknown_orders() is True

    history = await wal_store.load_history()
    assert len(history) == 2
    assert history[0]["event_type"] == "ORDER_INTENT"
    assert history[1]["event_type"] == "BROKER_UNKNOWN"
    assert history[1]["data"]["client_order_id"] == "ORD-UNK-01"
    assert history[1]["data"]["order_id"] == str(oid)
    assert history[1]["data"]["reason"] == "TIMEOUT_UNKNOWN"
    assert history[1]["data"]["status"] == OrderStatus.UNKNOWN.value


@pytest.mark.asyncio
async def test_recover_unknown_orders_open_accepted(tmp_path):
    """테스트 3: Broker OPEN/ACCEPTED 확정 결과 복구 및 UNKNOWN_RECOVERED WAL 기록 검증."""
    wal_file = str(tmp_path / "rec_open.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-REC-OPEN", qty=5)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-REC-OPEN")
    router.register_and_route(command=cmd, token=tok)
    router.mark_order_unknown("ORD-REC-OPEN")

    broker = MockBrokerAdapter()
    broker.status_map["ORD-REC-OPEN"] = {
        "client_order_id": "ORD-REC-OPEN",
        "broker_order_id": "BRK-991",
        "status": "ACCEPTED",
        "executed_qty": 0,
    }

    summary = router.recover_unknown_orders(broker)
    assert summary["unknown_checked"] == 1
    assert summary["recovered"] == 1
    assert summary["remained_unknown"] == 0

    assert router.fsm.get_status(oid) == OrderStatus.ACCEPTED
    assert router.has_unresolved_unknown_orders() is False

    history = await wal_store.load_history()
    assert len(history) == 3
    assert history[2]["event_type"] == "UNKNOWN_RECOVERED"
    assert history[2]["data"]["recovered_status"] == OrderStatus.ACCEPTED.value


@pytest.mark.asyncio
async def test_recover_unknown_orders_partial(tmp_path):
    """테스트 4: Broker PARTIAL 확정 결과 복구 및 누적체결수량 보존 검증."""
    wal_file = str(tmp_path / "rec_partial.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-REC-PART", qty=10)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-REC-PART")
    router.register_and_route(command=cmd, token=tok)
    router.mark_order_unknown("ORD-REC-PART")

    broker = MockBrokerAdapter()
    broker.status_map["ORD-REC-PART"] = {
        "client_order_id": "ORD-REC-PART",
        "status": "PARTIAL",
        "executed_qty": 4,
    }

    summary = router.recover_unknown_orders(broker)
    assert summary["recovered"] == 1
    assert router.fsm.get_status(oid) == OrderStatus.PARTIAL
    assert router.get_executed_qty(oid) == 4
    assert router.has_unresolved_unknown_orders() is False


@pytest.mark.asyncio
async def test_recover_unknown_orders_terminal_states(tmp_path):
    """테스트 5: Broker FILLED / CANCELLED / REJECTED 종료 확정 상태 복구 및 정리 검증."""
    wal_file = str(tmp_path / "rec_terminal.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    # 1. FILLED 복구
    cmd1 = make_cmd("ORD-T-FILL", qty=5)
    oid1 = uuid.uuid4()
    tok1 = make_token(oid1, "ORD-T-FILL")
    router.register_and_route(command=cmd1, token=tok1)
    router.mark_order_unknown("ORD-T-FILL")

    # 2. CANCELLED 복구
    cmd2 = make_cmd("ORD-T-CAN", qty=3)
    oid2 = uuid.uuid4()
    tok2 = make_token(oid2, "ORD-T-CAN")
    router.register_and_route(command=cmd2, token=tok2)
    router.mark_order_unknown("ORD-T-CAN")

    # 3. REJECTED 복구
    cmd3 = make_cmd("ORD-T-REJ", qty=2)
    oid3 = uuid.uuid4()
    tok3 = make_token(oid3, "ORD-T-REJ")
    router.register_and_route(command=cmd3, token=tok3)
    router.mark_order_unknown("ORD-T-REJ")

    broker = MockBrokerAdapter()
    broker.status_map["ORD-T-FILL"] = {"status": "FILLED", "executed_qty": 5}
    broker.status_map["ORD-T-CAN"] = {"status": "CANCELLED", "executed_qty": 0}
    broker.status_map["ORD-T-REJ"] = {"status": "REJECTED", "executed_qty": 0}

    summary = router.recover_unknown_orders(broker)
    assert summary["unknown_checked"] == 3
    assert summary["recovered"] == 3
    assert summary["remained_unknown"] == 0

    assert router.fsm.get_status(oid1) == OrderStatus.FILLED
    assert router.fsm.get_status(oid2) == OrderStatus.CANCELLED
    assert router.fsm.get_status(oid3) == OrderStatus.REJECTED
    assert router.has_unresolved_unknown_orders() is False


def test_recover_unknown_orders_unclear_maintains_unknown():
    """테스트 6: Broker 조회가 None/예외/불명확 응답인 경우 UNKNOWN 상태를 안전하게 유지하는지 검증."""
    router = OrderRouter()
    cmd = make_cmd("ORD-UNCLEAR-01", qty=5)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-UNCLEAR-01")
    router.register_and_route(command=cmd, token=tok)
    router.mark_order_unknown("ORD-UNCLEAR-01")

    # 1. Broker가 None을 반환하는 경우
    broker = MockBrokerAdapter()
    broker.status_map["ORD-UNCLEAR-01"] = None

    summary = router.recover_unknown_orders(broker)
    assert summary["unknown_checked"] == 1
    assert summary["recovered"] == 0
    assert summary["remained_unknown"] == 1
    assert router.fsm.get_status(oid) == OrderStatus.UNKNOWN
    assert router.has_unresolved_unknown_orders() is True

    # 2. Broker에서 예외가 발생하는 경우
    class ErrorBroker:
        def get_order_status(self, order_identifier: str = ""):
            raise ConnectionResetError("Broker gateway unreachable")

    summary2 = router.recover_unknown_orders(ErrorBroker())
    assert summary2["recovered"] == 0
    assert summary2["remained_unknown"] == 1
    assert router.fsm.get_status(oid) == OrderStatus.UNKNOWN
    assert router.has_unresolved_unknown_orders() is True


def test_safety_block_new_orders_when_unknown_remains():
    """테스트 7: 미해결 UNKNOWN 주문이 남아있을 때 has_unresolved_unknown_orders()가 True를 반환하여 안전 차단 활성화 검증."""
    runtime = OptionProgramRuntime()
    cmd = make_cmd("ORD-BLOCK-01", qty=5)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-BLOCK-01")
    runtime.order_router.register_and_route(command=cmd, token=tok)

    assert runtime.has_unresolved_unknown_orders() is False

    runtime.mark_order_unknown("ORD-BLOCK-01")
    assert runtime.has_unresolved_unknown_orders() is True


def test_recovery_idempotency():
    """테스트 8: recover_unknown_orders()를 반복 호출해도 중복 전이나 예외 없이 멱등적으로 동작하는지 검증."""
    router = OrderRouter()
    cmd = make_cmd("ORD-IDEMP-01", qty=5)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-IDEMP-01")
    router.register_and_route(command=cmd, token=tok)
    router.mark_order_unknown("ORD-IDEMP-01")

    broker = MockBrokerAdapter()
    broker.status_map["ORD-IDEMP-01"] = {"status": "ACCEPTED", "executed_qty": 0}

    # 1차 복구
    sum1 = router.recover_unknown_orders(broker)
    assert sum1["recovered"] == 1

    # 2차 복구 (이미 복구 완료되어 UNKNOWN이 없음)
    sum2 = router.recover_unknown_orders(broker)
    assert sum2["unknown_checked"] == 0
    assert sum2["recovered"] == 0
    assert router.fsm.get_status(oid) == OrderStatus.ACCEPTED
