"""tests/unit/test_runtime_wal_store_connection.py

[D-14] 기존 WalStore를 OptionProgramRuntime 및 OrderRouter FSM에 연결 검증 테스트 스위트.
- 테스트 1: OptionProgramRuntime 생성자 주입 시 OrderRouter.wal_store 바인딩 검증
- 테스트 2: handle_execution_report() 체결 시 save_event_sync()를 통한 WAL 기록 경로 검증
- 테스트 3: WAL 파일(JSONL)에 실제 이벤트(PARTIAL_EXECUTION, FILLED_EXECUTION) 직렬화 저장 검증
- 테스트 4: 기존 OrderRouter.recover_from_wal() 복원 무결성 검증
- 테스트 5: wal_store=None 환경에서 기존 런타임/테스트 완벽 호환성(Null Object 패턴) 검증
- 테스트 6: TradingSystem config(wal_log_path / wal_store)를 통한 종단간 초기화 주입 검증
"""

import uuid
import pytest
from infra.wal_store import WalStore
from option_program.runtime.program_runtime import OptionProgramRuntime
from option_program.orders.oms_fsm import OrderStatus
from option_program.orders.order_router import OrderRouter
from shared.core.contracts import RiskApprovalToken
from shared.contracts.canonical import (
    CanonicalAssetType,
    CanonicalExecutionReport,
    CanonicalOptionType,
    CanonicalOrderCommand,
    CanonicalOrderSide,
)
from main import TradingSystem


def make_command(client_id: str = "ORD-WAL-TEST-01", qty: int = 10, price: float = 3.0) -> CanonicalOrderCommand:
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


def make_token(order_uuid: uuid.UUID, client_id: str = "ORD-WAL-TEST-01") -> RiskApprovalToken:
    return RiskApprovalToken(
        order_id=order_uuid,
        timestamp_ns=1000000,
        signature=f"SIG-RISK-APPROVED-Track1-{client_id}",
    )


def make_exec_report(
    client_id: str,
    exec_id: str,
    executed_qty: int,
    executed_price: float = 3.0,
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
        timestamp="2026-08-31 09:00:00",
        symbol="201V3350",
    )


@pytest.mark.asyncio
async def test_wal_store_injection_into_runtime_and_router(tmp_path):
    """테스트 1: WalStore 인스턴스가 OptionProgramRuntime을 거쳐 OrderRouter에 정확히 주입되는지 검증."""
    wal_file = str(tmp_path / "orders.wal")
    wal_store = WalStore(log_path=wal_file)

    runtime = OptionProgramRuntime(wal_store=wal_store)

    # runtime과 order_router가 동일한 WalStore를 참조하는지 확인
    assert runtime.wal_store is wal_store
    assert runtime.order_router.wal_store is wal_store


@pytest.mark.asyncio
async def test_execution_report_persists_to_wal_via_runtime_path(tmp_path):
    """테스트 2 & 3: Runtime을 통한 체결 이벤트 처리 시 WalStore.save_event_sync()로 실제 파일에 기록되는지 검증."""
    wal_file = str(tmp_path / "orders_exec.wal")
    wal_store = WalStore(log_path=wal_file)

    runtime = OptionProgramRuntime(wal_store=wal_store)

    # 1. 주문 생성 및 등록
    cmd = make_command("ORD-D14-01", qty=10)
    order_uuid = uuid.uuid4()
    token = make_token(order_uuid, "ORD-D14-01")
    assigned_id = runtime.order_router.register_and_route(command=cmd, token=token)
    assert assigned_id == order_uuid

    # 2. 1차 부분 체결 (4주)
    rep1 = make_exec_report("ORD-D14-01", "EXEC-D14-101", executed_qty=4)
    runtime.order_router.handle_execution_report(order_uuid, rep1)

    # 3. 2차 전량 체결 (6주 추가 -> 총 10주 FILLED)
    rep2 = make_exec_report("ORD-D14-01", "EXEC-D14-102", executed_qty=6)
    runtime.order_router.handle_execution_report(order_uuid, rep2)

    # WAL 파일에 이벤트가 기록되었는지 확인 (ORDER_INTENT, PARTIAL_EXECUTION, FILLED_EXECUTION)
    history = await wal_store.load_history()
    assert len(history) == 3

    # 1차 이벤트: ORDER_INTENT
    assert history[0]["event_type"] == "ORDER_INTENT"
    assert history[0]["data"]["client_order_id"] == "ORD-D14-01"
    assert history[0]["data"]["qty"] == 10

    # 2차 이벤트: PARTIAL_EXECUTION
    assert history[1]["event_type"] == "PARTIAL_EXECUTION"
    assert history[1]["data"]["client_order_id"] == "ORD-D14-01"
    assert history[1]["data"]["cum_executed_qty"] == 4
    assert history[1]["data"]["exec_id"] == "EXEC-D14-101"

    # 3차 이벤트: FILLED_EXECUTION
    assert history[2]["event_type"] == "FILLED_EXECUTION"
    assert history[2]["data"]["client_order_id"] == "ORD-D14-01"
    assert history[2]["data"]["cum_executed_qty"] == 10
    assert history[2]["data"]["exec_id"] == "EXEC-D14-102"


@pytest.mark.asyncio
async def test_recover_from_wal_preserves_accumulated_state(tmp_path):
    """테스트 4: WalStore에 저장된 이력을 신규 OrderRouter에서 recover_from_wal()로 복원 시 상태 무결성 검증."""
    wal_file = str(tmp_path / "recovery_test.wal")
    wal_store = WalStore(log_path=wal_file)

    # 이전 세션 기록
    wal_store.save_event_sync("PARTIAL_EXECUTION", {
        "order_id": str(uuid.uuid4()),
        "client_order_id": "ORD-RECOVER-01",
        "cum_executed_qty": 3,
        "delta_executed_qty": 3,
        "exec_id": "EXEC-REC-01",
        "symbol": "201V3350",
    })

    history = await wal_store.load_history()
    assert len(history) == 1

    # 새 세션 런타임 생성 및 복원
    new_runtime = OptionProgramRuntime(wal_store=wal_store)
    recovered_count = new_runtime.order_router.recover_from_wal(history)
    assert recovered_count == 1

    # 복원된 상태 확인
    assert new_runtime.order_router.is_execution_processed("EXEC-REC-01") is True
    assert new_runtime.order_router._client_to_executed_qty.get("ORD-RECOVER-01") == 3


def test_default_runtime_has_wal_store_connected():
    """테스트 5: 기본 OptionProgramRuntime() 생성 시 WalStore가 자동으로 연결되고 OrderRouter와 동일 인스턴스를 공유하는지 검증."""
    runtime = OptionProgramRuntime()
    assert runtime.wal_store is not None
    assert runtime.order_router.wal_store is runtime.wal_store
    assert hasattr(runtime.wal_store, "save_event_sync")

    # OrderRouter 단독 wal_store=None 환경에서도 Null-Object 안전 동작 검증
    router_none = OrderRouter(wal_store=None)
    cmd = make_command("ORD-NOWAL-01", qty=5)
    order_uuid = uuid.uuid4()
    token = make_token(order_uuid, "ORD-NOWAL-01")
    assigned_id = router_none.register_and_route(command=cmd, token=token)
    assert assigned_id == order_uuid

    rep = make_exec_report("ORD-NOWAL-01", "EXEC-NOWAL-01", executed_qty=5)
    router_none.handle_execution_report(order_uuid, rep)
    assert router_none.fsm.get_status(order_uuid) == OrderStatus.FILLED


@pytest.mark.asyncio
async def test_trading_system_initialization_with_wal_path(tmp_path):
    """테스트 6: TradingSystem.initialize()를 통해 wal_log_path 설정이 OptionProgramRuntime에 전달되는지 검증."""
    wal_file = str(tmp_path / "system_orders.wal")
    config = {
        "broker_mode": "PAPER",
        "initial_capital": 50_000_000.0,
        "wal_log_path": wal_file,
    }
    system = TradingSystem(config=config)
    await system.initialize()

    try:
        assert system.op_runtime is not None
        assert system.op_runtime.wal_store is not None
        assert system.op_runtime.order_router.wal_store is not None
        assert system.op_runtime.wal_store.log_path == wal_file
    finally:
        if system.broker:
            system.broker.disconnect()


@pytest.mark.asyncio
async def test_trading_system_initialization_with_default_wal_path():
    """테스트 7: TradingSystem.initialize() 설정에 wal_log_path가 없어도 기본 WalStore가 생성 및 주입되는지 검증."""
    config = {
        "broker_mode": "PAPER",
        "initial_capital": 50_000_000.0,
    }
    system = TradingSystem(config=config)
    await system.initialize()

    try:
        assert system.op_runtime is not None
        assert system.op_runtime.wal_store is not None
        assert system.op_runtime.order_router.wal_store is not None
        assert system.op_runtime.wal_store is system.op_runtime.order_router.wal_store
        assert "orders.wal" in system.op_runtime.wal_store.log_path
    finally:
        if system.broker:
            system.broker.disconnect()
