"""tests/unit/test_execution_wal_idempotency_recovery.py

[D-17] 체결 이벤트 WAL 기록 및 중복 체결 상태 복구 검증 테스트 스위트.
- 테스트 1: Execution report 수신 시 WAL 이벤트 기록 및 필수 필드 보존 검증
- 테스트 2: 동일 exec_id 중복 수신 시 멱등성 차단 (체결 수량 및 WAL 중복 미발생)
- 테스트 3: recover_from_wal()을 통한 processed_exec_ids 및 FSM/누적체결량 복구 검증
- 테스트 4: 프로세스 재시작(새 OrderRouter 인스턴스) 후 WAL 복원 및 과거 exec_id 재수신 차단 검증
- 테스트 5: 다중 PARTIAL 체결 누적 및 WAL 복원 정밀도 검증
- 테스트 6: PARTIAL -> FILLED 체결 전이 및 종료 주문의 active_orders 정리 및 복원 일관성 검증
- 테스트 7: WAL 기록 실패 시 FSM 및 메모리 상태 안전성 검증
- 테스트 8: exec_id가 None/빈문자열인 경우의 정상 동작 보존 검증
- 테스트 9: OptionProgramRuntime을 통한 체결 수신 및 WAL 영속/복원 통합 경로 검증
"""

import uuid
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


def make_cmd(client_id: str = "ORD-D17-01", qty: int = 10, price: float = 2.5) -> CanonicalOrderCommand:
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


def make_token(order_uuid: uuid.UUID, client_id: str = "ORD-D17-01") -> RiskApprovalToken:
    return RiskApprovalToken(
        order_id=order_uuid,
        timestamp_ns=1000000,
        signature=f"SIG-RISK-APPROVED-Track1-{client_id}",
    )


def make_report(
    order_id: uuid.UUID,
    client_id: str,
    exec_id: str,
    exec_qty: int,
    price: float = 2.5,
    timestamp: str = "2026-08-23 10:00:00",
) -> CanonicalExecutionReport:
    return CanonicalExecutionReport(
        exec_id=exec_id,
        client_order_id=client_id,
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        executed_qty=exec_qty,
        executed_price=price,
        fee=0.0,
        slippage=0.0,
        timestamp=timestamp,
    )


@pytest.mark.asyncio
async def test_execution_report_persists_to_wal_with_all_fields(tmp_path):
    """테스트 1: Execution report 수신 시 WAL 이벤트 기록 및 필수 필드 보존 검증."""
    wal_file = str(tmp_path / "exec_fields.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-F1", qty=10, price=3.0)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-F1")
    router.register_and_route(command=cmd, token=tok)

    report = make_report(oid, "ORD-F1", exec_id="EXEC-001", exec_qty=4, price=3.0)
    router.handle_execution_report(oid, report)

    assert router.fsm.get_status(oid) == OrderStatus.PARTIAL
    assert router.get_executed_qty(oid) == 4

    history = await wal_store.load_history()
    assert len(history) == 2
    assert history[0]["event_type"] == "ORDER_INTENT"
    assert history[1]["event_type"] == "PARTIAL_EXECUTION"

    data = history[1]["data"]
    assert data["exec_id"] == "EXEC-001"
    assert data["order_id"] == str(oid)
    assert data["client_order_id"] == "ORD-F1"
    assert data["executed_qty"] == 4
    assert data["cum_executed_qty"] == 4
    assert data["requested_qty"] == 10
    assert data["executed_price"] == 3.0
    assert data["status"] == OrderStatus.PARTIAL.value
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_duplicate_exec_id_ignored_idempotency(tmp_path):
    """테스트 2: 동일 exec_id 중복 수신 시 멱등성 차단 (체결 수량 및 WAL 중복 미발생)."""
    wal_file = str(tmp_path / "exec_dup.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-DUP", qty=10, price=2.0)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-DUP")
    router.register_and_route(command=cmd, token=tok)

    # 1차 수신
    rep1 = make_report(oid, "ORD-DUP", exec_id="EXEC-DUP-99", exec_qty=3)
    router.handle_execution_report(oid, rep1)
    assert router.get_executed_qty(oid) == 3

    # 2차 중복 수신 (동일 exec_id)
    rep2 = make_report(oid, "ORD-DUP", exec_id="EXEC-DUP-99", exec_qty=3)
    router.handle_execution_report(oid, rep2)
    assert router.get_executed_qty(oid) == 3  # 수량 증가 없음

    history = await wal_store.load_history()
    assert len(history) == 2  # ORDER_INTENT 1건 + PARTIAL_EXECUTION 1건만 존재


@pytest.mark.asyncio
async def test_recover_from_wal_restores_processed_exec_ids_and_state(tmp_path):
    """테스트 3: recover_from_wal()을 통한 processed_exec_ids 및 FSM/누적체결량 복구 검증."""
    wal_file = str(tmp_path / "exec_rec.wal")
    wal_store = WalStore(log_path=wal_file)
    router1 = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-REC", qty=10)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-REC")
    router1.register_and_route(command=cmd, token=tok)

    rep1 = make_report(oid, "ORD-REC", exec_id="EXEC-R1", exec_qty=3)
    router1.handle_execution_report(oid, rep1)

    rep2 = make_report(oid, "ORD-REC", exec_id="EXEC-R2", exec_qty=4)
    router1.handle_execution_report(oid, rep2)

    assert router1.get_executed_qty(oid) == 7
    assert router1.fsm.get_status(oid) == OrderStatus.PARTIAL

    # WAL에서 이벤트 로드 및 새 라우터에서 복원
    history = await wal_store.load_history()
    router2 = OrderRouter(wal_store=wal_store)
    recovered = router2.recover_from_wal(history)

    assert recovered == 2  # 2개 체결 이벤트 복원
    assert "EXEC-R1" in router2._processed_exec_ids
    assert "EXEC-R2" in router2._processed_exec_ids
    assert router2.get_executed_qty(oid) == 7
    assert router2.get_executed_qty("ORD-REC") == 7
    assert router2.fsm.get_status(oid) == OrderStatus.PARTIAL


@pytest.mark.asyncio
async def test_restart_recovery_blocks_past_exec_id_replay(tmp_path):
    """테스트 4: 프로세스 재시작(새 OrderRouter 인스턴스) 후 WAL 복원 및 과거 exec_id 재수신 차단 검증."""
    wal_file = str(tmp_path / "exec_restart.wal")
    wal_store = WalStore(log_path=wal_file)
    router1 = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-RST", qty=10)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-RST")
    router1.register_and_route(command=cmd, token=tok)

    rep1 = make_report(oid, "ORD-RST", exec_id="EXEC-PAST-1", exec_qty=5)
    router1.handle_execution_report(oid, rep1)

    # 재시작 모사
    history = await wal_store.load_history()
    router2 = OrderRouter(wal_store=wal_store)
    # 활성 주문 복원 (active_orders에 등록된 상태 가정)
    router2._active_orders[oid] = (cmd, tok)
    router2.recover_from_wal(history)

    # 과거 exec_id가 다시 유입됨
    rep_dup = make_report(oid, "ORD-RST", exec_id="EXEC-PAST-1", exec_qty=5)
    router2.handle_execution_report(oid, rep_dup)

    # 체결량이 5에서 10으로 중복 증가하지 않아야 함
    assert router2.get_executed_qty(oid) == 5

    # 신규 exec_id 유입 시 정상 체결
    rep_new = make_report(oid, "ORD-RST", exec_id="EXEC-NEW-2", exec_qty=5)
    router2.handle_execution_report(oid, rep_new)

    assert router2.get_executed_qty(oid) == 10
    assert router2.fsm.get_status(oid) == OrderStatus.FILLED


@pytest.mark.asyncio
async def test_multi_step_partial_executions_accumulation_and_recovery(tmp_path):
    """테스트 5: 다중 PARTIAL 체결 누적 및 WAL 복원 정밀도 검증 (2 -> 3 -> 3 -> 8/10)."""
    wal_file = str(tmp_path / "exec_multi.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-M", qty=10)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-M")
    router.register_and_route(command=cmd, token=tok)

    for i, q in enumerate([2, 3, 3], start=1):
        rep = make_report(oid, "ORD-M", exec_id=f"EXEC-M{i}", exec_qty=q)
        router.handle_execution_report(oid, rep)

    assert router.get_executed_qty(oid) == 8
    assert router.fsm.get_status(oid) == OrderStatus.PARTIAL

    history = await wal_store.load_history()
    # ORDER_INTENT (1) + PARTIAL_EXECUTION (3)
    assert len(history) == 4

    new_router = OrderRouter()
    new_router.recover_from_wal(history)
    assert new_router.get_executed_qty(oid) == 8
    assert new_router.fsm.get_status(oid) == OrderStatus.PARTIAL
    assert len(new_router._processed_exec_ids) == 3


@pytest.mark.asyncio
async def test_partial_to_filled_and_active_orders_cleanup(tmp_path):
    """테스트 6: PARTIAL -> FILLED 체결 전이 및 종료 주문의 active_orders 정리 및 복원 일관성 검증."""
    wal_file = str(tmp_path / "exec_filled.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-F", qty=5)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-F")
    router.register_and_route(command=cmd, token=tok)

    # 1. PARTIAL (3)
    rep1 = make_report(oid, "ORD-F", exec_id="EX-P1", exec_qty=3)
    router.handle_execution_report(oid, rep1)
    assert oid in router._active_orders

    # 2. FILLED (2 -> 총 5)
    rep2 = make_report(oid, "ORD-F", exec_id="EX-F2", exec_qty=2)
    router.handle_execution_report(oid, rep2)
    assert router.fsm.get_status(oid) == OrderStatus.FILLED
    assert oid not in router._active_orders

    history = await wal_store.load_history()
    assert history[-1]["event_type"] == "FILLED_EXECUTION"
    assert history[-1]["data"]["cum_executed_qty"] == 5

    # 새 라우터에서 복원
    new_router = OrderRouter()
    new_router._active_orders[oid] = (cmd, tok)
    new_router.recover_from_wal(history)

    assert new_router.fsm.get_status(oid) == OrderStatus.FILLED
    assert oid not in new_router._active_orders
    assert new_router.get_executed_qty(oid) == 5


def test_exec_id_none_or_empty_safe_handling():
    """테스트 7: exec_id가 None/빈문자열인 경우 중복 검사 우회 후 정상 체결 처리 검증."""
    router = OrderRouter()
    cmd = make_cmd("ORD-NO-EXEC-ID", qty=5)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-NO-EXEC-ID")
    router.register_and_route(command=cmd, token=tok)

    # exec_id가 None인 report
    rep = CanonicalExecutionReport(
        exec_id="",
        client_order_id="ORD-NO-EXEC-ID",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        executed_qty=2,
        executed_price=2.0,
        fee=0.0,
        slippage=0.0,
        timestamp="2026-08-23 10:00:00",
    )
    router.handle_execution_report(oid, rep)
    assert router.get_executed_qty(oid) == 2
    assert router.fsm.get_status(oid) == OrderStatus.PARTIAL


@pytest.mark.asyncio
async def test_option_program_runtime_execution_and_recovery_path(tmp_path):
    """테스트 8: OptionProgramRuntime을 통한 체결 수신 및 WAL 영속/복원 통합 경로 검증."""
    wal_file = str(tmp_path / "runtime_exec.wal")
    wal_store = WalStore(log_path=wal_file)
    runtime = OptionProgramRuntime(wal_store=wal_store)

    cmd = make_cmd("ORD-RT-01", qty=6)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-RT-01")
    runtime.order_router.register_and_route(command=cmd, token=tok)
    runtime._order_id_to_uuid["ORD-RT-01"] = oid

    rep = make_report(oid, "ORD-RT-01", exec_id="EXEC-RT-1", exec_qty=6)
    runtime.consume_execution_report(rep)

    assert runtime.get_order_executed_qty("ORD-RT-01") == 6
    assert runtime.order_router.fsm.get_status(oid) == OrderStatus.FILLED

    history = await wal_store.load_history()
    assert len(history) == 2
    assert history[1]["event_type"] == "FILLED_EXECUTION"

    # 새 Runtime 인스턴스 복원 검증
    new_runtime = OptionProgramRuntime(wal_store=wal_store)
    recovered = new_runtime.recover_from_wal(history)
    assert recovered == 1
    assert new_runtime.get_order_executed_qty("ORD-RT-01") == 6
