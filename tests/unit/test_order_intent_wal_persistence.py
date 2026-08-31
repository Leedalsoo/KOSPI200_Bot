"""tests/unit/test_order_intent_wal_persistence.py

[D-15] Broker 전송 전 ORDER_INTENT 및 BROKER_SEND_STARTED WAL 기록 검증 테스트 스위트.
- 테스트 1: register_and_route() 시 ORDER_INTENT 이벤트 WAL 영속화 검증
- 테스트 2: Broker send_order() 직전 BROKER_SEND_STARTED 이벤트 WAL 영속화 검증
- 테스트 3: ORDER_INTENT ➔ BROKER_SEND_STARTED ➔ 체결(PARTIAL/FILLED) 전체 WAL 시퀀스 무결성 검증
- 테스트 4: ORDER_INTENT WAL 저장 실패 시 안전한 주문 등록 차단 및 FSM REJECTED 전이 검증
- 테스트 5: BROKER_SEND_STARTED WAL 저장 실패 시 TradingSystem의 Broker 발주 차단 검증
- 테스트 6: wal_store=None (가상/테스트 환경) Null Object 안전성 및 기존 계약 보존 검증
"""

import uuid
import pytest
from infra.wal_store import WalStore
from option_program.runtime.program_runtime import OptionProgramRuntime
from option_program.orders.order_router import OrderRouter
from option_program.orders.oms_fsm import OrderStatus
from shared.core.contracts import RiskApprovalToken
from shared.contracts.canonical import (
    CanonicalAssetType,
    CanonicalExecutionReport,
    CanonicalOptionType,
    CanonicalOrderCommand,
    CanonicalOrderSide,
)
from main import TradingSystem


def make_cmd(client_id: str = "ORD-D15-01", qty: int = 5, price: float = 3.2) -> CanonicalOrderCommand:
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


def make_token(order_uuid: uuid.UUID, client_id: str = "ORD-D15-01") -> RiskApprovalToken:
    return RiskApprovalToken(
        order_id=order_uuid,
        timestamp_ns=1000000,
        signature=f"SIG-RISK-APPROVED-Track1-{client_id}",
    )


def make_report(
    client_id: str,
    exec_id: str,
    executed_qty: int,
    executed_price: float = 3.2,
) -> CanonicalExecutionReport:
    return CanonicalExecutionReport(
        exec_id=exec_id,
        client_order_id=client_id,
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        executed_qty=executed_qty,
        executed_price=executed_price,
        fee=100.0,
        slippage=0.0,
        timestamp="2026-09-01 09:00:00",
        symbol="201V3350",
    )


@pytest.mark.asyncio
async def test_order_intent_persists_on_register_and_route(tmp_path):
    """테스트 1: OrderRouter.register_and_route() 호출 시 ORDER_INTENT가 WAL에 즉시 기록되는지 검증."""
    wal_file = str(tmp_path / "order_intent.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-INTENT-01", qty=5, price=2.5)
    order_uuid = uuid.uuid4()
    token = make_token(order_uuid, "ORD-INTENT-01")

    assigned_id = router.register_and_route(command=cmd, token=token)
    assert assigned_id == order_uuid

    history = await wal_store.load_history()
    assert len(history) == 1
    event = history[0]
    assert event["event_type"] == "ORDER_INTENT"
    assert event["data"]["order_id"] == str(order_uuid)
    assert event["data"]["client_order_id"] == "ORD-INTENT-01"
    assert event["data"]["qty"] == 5
    assert event["data"]["price"] == 2.5
    assert event["data"]["status"] == OrderStatus.SENT.value


@pytest.mark.asyncio
async def test_broker_send_started_persists_before_send(tmp_path):
    """테스트 2: Broker send_order() 직전에 persist_broker_send_started()가 BROKER_SEND_STARTED를 영속화하는지 검증."""
    wal_file = str(tmp_path / "send_started.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-SEND-01", qty=10, price=3.5)
    order_uuid = uuid.uuid4()
    token = make_token(order_uuid, "ORD-SEND-01")
    router.register_and_route(command=cmd, token=token)

    ok = router.persist_broker_send_started(cmd)
    assert ok is True

    history = await wal_store.load_history()
    assert len(history) == 2
    assert history[0]["event_type"] == "ORDER_INTENT"
    assert history[1]["event_type"] == "BROKER_SEND_STARTED"
    assert history[1]["data"]["client_order_id"] == "ORD-SEND-01"
    assert history[1]["data"]["order_id"] == str(order_uuid)
    assert history[1]["data"]["qty"] == 10


@pytest.mark.asyncio
async def test_full_order_send_wal_lifecycle_sequence(tmp_path):
    """테스트 3: ORDER_INTENT ➔ BROKER_SEND_STARTED ➔ 체결(PARTIAL/FILLED) 전체 WAL 시퀀스 순서와 무결성 검증."""
    wal_file = str(tmp_path / "full_lifecycle.wal")
    wal_store = WalStore(log_path=wal_file)
    runtime = OptionProgramRuntime(wal_store=wal_store)

    # 1. 주문 발주 (ORDER_INTENT)
    cmd = make_cmd("ORD-SEQ-01", qty=10, price=3.0)
    order_uuid = uuid.uuid4()
    token = make_token(order_uuid, "ORD-SEQ-01")
    runtime.order_router.register_and_route(command=cmd, token=token)

    # 2. 브로커 전송 시작 (BROKER_SEND_STARTED)
    runtime.persist_broker_send_started(cmd)

    # 3. 1차 부분체결 (4주)
    rep1 = make_report("ORD-SEQ-01", "EXEC-SEQ-101", executed_qty=4)
    runtime.order_router.handle_execution_report(order_uuid, rep1)

    # 4. 2차 전량체결 (6주 -> 총 10주)
    rep2 = make_report("ORD-SEQ-01", "EXEC-SEQ-102", executed_qty=6)
    runtime.order_router.handle_execution_report(order_uuid, rep2)

    # 5. WAL 검증
    history = await wal_store.load_history()
    assert len(history) == 4
    assert [h["event_type"] for h in history] == [
        "ORDER_INTENT",
        "BROKER_SEND_STARTED",
        "PARTIAL_EXECUTION",
        "FILLED_EXECUTION",
    ]


@pytest.mark.asyncio
async def test_order_intent_wal_failure_aborts_order_registration():
    """테스트 4: ORDER_INTENT WAL 저장 실패 시 주문 등록을 중단하고 REJECTED 처리하는지 검증."""
    class FailingWalStore:
        def save_event_sync(self, event_type, data):
            raise IOError("Disk full: cannot write WAL")

    router = OrderRouter(wal_store=FailingWalStore())
    cmd = make_cmd("ORD-FAIL-01", qty=5)
    order_uuid = uuid.uuid4()
    token = make_token(order_uuid, "ORD-FAIL-01")

    assigned_id = router.register_and_route(command=cmd, token=token)
    # WAL 실패 시 복원 근거 없는 주문 생성 차단 (None 반환)
    assert assigned_id is None
    assert router.fsm.get_status(order_uuid) == OrderStatus.REJECTED
    assert order_uuid not in router._active_orders


@pytest.mark.asyncio
async def test_broker_send_started_wal_failure_returns_false():
    """테스트 5: BROKER_SEND_STARTED WAL 저장 실패 시 persist_broker_send_started가 False를 반환하여 전송을 차단하는지 검증."""
    class FailingWalStore:
        def save_event_sync(self, event_type, data):
            raise IOError("Network disk disconnected: cannot write WAL")

    router = OrderRouter(wal_store=FailingWalStore())
    cmd = make_cmd("ORD-FAIL-02", qty=5)
    ok = router.persist_broker_send_started(cmd)
    assert ok is False


def test_wal_store_none_null_object_safety():
    """테스트 6: wal_store=None 환경에서 ORDER_INTENT 및 BROKER_SEND_STARTED가 예외 없이 통과하는지 검증."""
    router = OrderRouter(wal_store=None)
    cmd = make_cmd("ORD-NONE-01", qty=3)
    order_uuid = uuid.uuid4()
    token = make_token(order_uuid, "ORD-NONE-01")

    assigned_id = router.register_and_route(command=cmd, token=token)
    assert assigned_id == order_uuid
    assert router.fsm.get_status(order_uuid) == OrderStatus.SENT

    ok = router.persist_broker_send_started(cmd)
    assert ok is True


@pytest.mark.asyncio
async def test_default_runtime_persists_order_intent_and_send_started_to_wal(tmp_path):
    """테스트 7: 실제 런타임 경로(OptionProgramRuntime ➔ OrderRouter)에서 ORDER_INTENT ➔ BROKER_SEND_STARTED 순서 기록 검증."""
    wal_file = str(tmp_path / "runtime_path_test.wal")
    wal_store = WalStore(log_path=wal_file)
    runtime = OptionProgramRuntime(wal_store=wal_store)

    assert runtime.wal_store is wal_store
    assert runtime.order_router.wal_store is wal_store

    # 1. 전략 주문 등록 ➔ ORDER_INTENT 영속화
    cmd = make_cmd("ORD-RT-01", qty=7, price=4.2)
    order_uuid = uuid.uuid4()
    token = make_token(order_uuid, "ORD-RT-01")
    assigned_id = runtime.order_router.register_and_route(command=cmd, token=token)
    assert assigned_id == order_uuid

    # 2. 브로커 전송 직전 ➔ BROKER_SEND_STARTED 영속화
    send_ok = runtime.persist_broker_send_started(cmd)
    assert send_ok is True

    # 3. WAL 파일 기록 검증
    history = await wal_store.load_history()
    assert len(history) == 2
    assert history[0]["event_type"] == "ORDER_INTENT"
    assert history[0]["data"]["client_order_id"] == "ORD-RT-01"
    assert history[0]["data"]["order_id"] == str(order_uuid)
    assert history[0]["data"]["qty"] == 7
    assert history[0]["data"]["price"] == 4.2

    assert history[1]["event_type"] == "BROKER_SEND_STARTED"
    assert history[1]["data"]["client_order_id"] == "ORD-RT-01"
    assert history[1]["data"]["order_id"] == str(order_uuid)
    assert history[1]["data"]["qty"] == 7
