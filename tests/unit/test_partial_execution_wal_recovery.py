"""Unit tests for D-10 Partial Execution State Persistence and WAL Recovery.

Verifies:
1. handle_execution_report() persists PARTIAL and FILLED execution events to WalStore
2. Restart simulation: New OrderRouter instance recovers cumulative execution state from WAL
3. Recovery correctly restores _cum_executed_qty, _executed_qty_history, _client_to_executed_qty, _processed_exec_ids, and FSM states
4. Continued execution after recovery: PARTIAL -> additional execution -> PARTIAL -> FILLED progression
5. Idempotency: Duplicate exec_id after recovery is ignored without double accumulation
6. Terminal state recovery: FILLED orders are marked as FILLED with cumulative history preserved
"""
import uuid
import pytest
from shared.core.contracts import OrderStatus, RiskApprovalToken
from shared.contracts.canonical import (
    CanonicalOrderCommand,
    CanonicalExecutionReport,
    CanonicalAssetType,
    CanonicalOrderSide,
)
from option_program.orders.order_router import OrderRouter
from infra.wal_store import WalStore


def make_cmd(client_id: str = "ORD-WAL-001", qty: int = 10, price: float = 3.5) -> CanonicalOrderCommand:
    return CanonicalOrderCommand(
        client_order_id=client_id,
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=qty,
        price=price,
        symbol="KOSPI200",
    )


def make_token(order_uuid: uuid.UUID, client_id: str = "ORD-WAL-001") -> RiskApprovalToken:
    return RiskApprovalToken(
        order_id=order_uuid,
        timestamp_ns=1000000,
        signature=f"SIG-RISK-APPROVED-Track1-{client_id}",
    )


def make_report(
    client_id: str,
    exec_id: str,
    executed_qty: int,
    executed_price: float = 3.5,
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
        symbol="KOSPI200",
    )


@pytest.mark.asyncio
async def test_partial_execution_wal_persistence_and_recovery_progression(tmp_path):
    """1. 부분 체결 WAL 기록 및 재기동 후 복원, 추가 체결을 통한 완결 검증."""
    wal_file = str(tmp_path / "test_exec.wal")
    wal_store = WalStore(log_path=wal_file)

    # 1. 초기 Router 생성 및 주문 발주 (10주 요청)
    router1 = OrderRouter(wal_store=wal_store)
    cmd = make_cmd("ORD-REC-001", qty=10)
    oid = uuid.uuid4()
    token = make_token(oid, "ORD-REC-001")
    router1.register_and_route(command=cmd, token=token)

    # 2. 1차 체결 수신 (4주 -> PARTIAL)
    rep1 = make_report("ORD-REC-001", "EXEC-001", executed_qty=4)
    router1.handle_execution_report(oid, rep1)
    assert router1.fsm.get_status(oid) == OrderStatus.PARTIAL
    assert router1._cum_executed_qty[oid] == 4

    # WAL 파일에 이벤트가 기록되었는지 확인 (ORDER_INTENT + PARTIAL_EXECUTION)
    history = await wal_store.load_history()
    assert len(history) == 2
    assert history[0]["event_type"] == "ORDER_INTENT"
    assert history[1]["event_type"] == "PARTIAL_EXECUTION"
    assert history[1]["data"]["cum_executed_qty"] == 4
    assert history[1]["data"]["exec_id"] == "EXEC-001"

    # 3. 프로세스 재시작 시뮬레이션: 신규 Router 인스턴스 생성 및 WAL 복원
    router2 = OrderRouter(wal_store=wal_store)
    # 복원 전에는 아무것도 없음
    assert router2.get_executed_qty(oid) == 0
    assert router2.is_execution_processed("EXEC-001") is False

    # WAL로부터 복원 실행
    recovered_count = router2.recover_from_wal(history)
    assert recovered_count == len(history)
    assert router2.fsm.get_status(oid) == OrderStatus.PARTIAL
    assert router2._cum_executed_qty[oid] == 4
    assert router2.get_executed_qty(oid) == 4
    assert router2.get_executed_qty("ORD-REC-001") == 4
    assert router2.is_execution_processed("EXEC-001") is True

    # 주문 정보 복원을 위해 active_orders 재등록
    router2._active_orders[oid] = (cmd, 1000.0)

    # 4. 중복 exec_id 재수신 시 멱등성 검증 (EXEC-001 재도착 시 누적되지 않음)
    router2.handle_execution_report(oid, rep1)
    assert router2.fsm.get_status(oid) == OrderStatus.PARTIAL
    assert router2._cum_executed_qty[oid] == 4

    # 5. 복원된 상태에서 2차 체결 수신 (3주 -> 누적 7주 PARTIAL)
    rep2 = make_report("ORD-REC-001", "EXEC-002", executed_qty=3)
    router2.handle_execution_report(oid, rep2)
    assert router2.fsm.get_status(oid) == OrderStatus.PARTIAL
    assert router2._cum_executed_qty[oid] == 7
    assert router2.get_executed_qty(oid) == 7

    # 6. 3차 체결 수신 (3주 -> 누적 10주 FILLED 완결)
    rep3 = make_report("ORD-REC-001", "EXEC-003", executed_qty=3)
    router2.handle_execution_report(oid, rep3)
    assert router2.fsm.get_status(oid) == OrderStatus.FILLED
    assert oid not in router2._active_orders
    assert router2.get_executed_qty(oid) == 10
    assert router2.get_executed_qty("ORD-REC-001") == 10

    # WAL 전체 이벤트 검증 (ORDER_INTENT + 3개 체결 = 총 4개 이벤트)
    final_history = await wal_store.load_history()
    assert len(final_history) == 4
    assert final_history[0]["event_type"] == "ORDER_INTENT"
    assert final_history[1]["event_type"] == "PARTIAL_EXECUTION"
    assert final_history[2]["event_type"] == "PARTIAL_EXECUTION"
    assert final_history[2]["data"]["cum_executed_qty"] == 7
    assert final_history[3]["event_type"] == "FILLED_EXECUTION"
    assert final_history[3]["data"]["cum_executed_qty"] == 10


@pytest.mark.asyncio
async def test_filled_order_recovery_state_integrity(tmp_path):
    """2. 이미 FILLED된 주문의 WAL 복원 무결성 검증."""
    wal_file = str(tmp_path / "test_filled.wal")
    wal_store = WalStore(log_path=wal_file)

    router1 = OrderRouter(wal_store=wal_store)
    cmd = make_cmd("ORD-FILL-001", qty=5)
    oid = uuid.uuid4()
    token = make_token(oid, "ORD-FILL-001")
    router1.register_and_route(command=cmd, token=token)

    # 1회 전량 체결
    rep = make_report("ORD-FILL-001", "EXEC-FULL-1", executed_qty=5)
    router1.handle_execution_report(oid, rep)
    assert router1.fsm.get_status(oid) == OrderStatus.FILLED

    history = await wal_store.load_history()
    assert len(history) == 2
    assert history[0]["event_type"] == "ORDER_INTENT"
    assert history[1]["event_type"] == "FILLED_EXECUTION"

    # 복원
    router2 = OrderRouter(wal_store=wal_store)
    recovered = router2.recover_from_wal(history)
    assert recovered == len(history)
    assert router2.fsm.get_status(oid) == OrderStatus.FILLED
    assert router2.get_executed_qty(oid) == 5
    assert router2.get_executed_qty("ORD-FILL-001") == 5
    assert oid not in router2._cum_executed_qty
    assert oid not in router2._active_orders


@pytest.mark.asyncio
async def test_multi_order_mixed_state_wal_recovery(tmp_path):
    """3. 복수 주문의 혼합 상태(PARTIAL, FILLED) 동시 WAL 복원 검증."""
    wal_file = str(tmp_path / "test_multi.wal")
    wal_store = WalStore(log_path=wal_file)

    router1 = OrderRouter(wal_store=wal_store)

    # 주문 A (10주 요청) -> 3주 체결 (PARTIAL)
    oid_a = uuid.uuid4()
    cmd_a = make_cmd("ORD-MIX-A", qty=10)
    tok_a = make_token(oid_a, "ORD-MIX-A")
    router1.register_and_route(cmd_a, tok_a)
    router1.handle_execution_report(oid_a, make_report("ORD-MIX-A", "EXEC-A1", executed_qty=3))

    # 주문 B (5주 요청) -> 5주 체결 (FILLED)
    oid_b = uuid.uuid4()
    cmd_b = make_cmd("ORD-MIX-B", qty=5)
    tok_b = make_token(oid_b, "ORD-MIX-B")
    router1.register_and_route(cmd_b, tok_b)
    router1.handle_execution_report(oid_b, make_report("ORD-MIX-B", "EXEC-B1", executed_qty=5))

    history = await wal_store.load_history()
    assert len(history) == 4
    assert [h["event_type"] for h in history] == [
        "ORDER_INTENT",
        "PARTIAL_EXECUTION",
        "ORDER_INTENT",
        "FILLED_EXECUTION",
    ]

    # 신규 Router 인스턴스에서 복원
    router2 = OrderRouter(wal_store=wal_store)
    count = router2.recover_from_wal(history)
    assert count == len(history)

    # 주문 A 검증 (PARTIAL, 3/10)
    assert router2.fsm.get_status(oid_a) == OrderStatus.PARTIAL
    assert router2.get_executed_qty(oid_a) == 3
    assert router2.get_executed_qty("ORD-MIX-A") == 3
    assert router2._cum_executed_qty[oid_a] == 3
    assert router2.is_execution_processed("EXEC-A1") is True

    # 주문 B 검증 (FILLED, 5/5)
    assert router2.fsm.get_status(oid_b) == OrderStatus.FILLED
    assert router2.get_executed_qty(oid_b) == 5
    assert router2.get_executed_qty("ORD-MIX-B") == 5
    assert oid_b not in router2._cum_executed_qty
    assert router2.is_execution_processed("EXEC-B1") is True


def test_corrupt_wal_event_tolerance_during_recovery():
    """4. 비정상/오염된 WAL 이벤트 레코드 수신 시 안전 회피 및 정상 복원 검증."""
    router = OrderRouter()
    oid_valid = uuid.uuid4()

    corrupt_events = [
        "not-a-dict",
        {"event_type": "UNKNOWN_EVENT", "data": {}},
        {"event_type": "PARTIAL_EXECUTION", "data": {"order_id": "invalid-uuid", "cum_executed_qty": 2}},
        {
            "event_type": "PARTIAL_EXECUTION",
            "data": {
                "exec_id": "EXEC-VALID-1",
                "order_id": str(oid_valid),
                "client_order_id": "ORD-VALID-1",
                "cum_executed_qty": 4,
                "status": "PARTIAL",
            },
        },
    ]

    count = router.recover_from_wal(corrupt_events)
    assert count == 2  # UNKNOWN_EVENT 제외 유효/처리 시도된 2건
    assert router.fsm.get_status(oid_valid) == OrderStatus.PARTIAL
    assert router.get_executed_qty(oid_valid) == 4
    assert router.is_execution_processed("EXEC-VALID-1") is True


def test_wal_store_none_backward_compatibility():
    """5. wal_store=None 설정 시 예외 없이 기존 인메모리 동작 유지 검증."""
    router = OrderRouter(wal_store=None)
    cmd = make_cmd("ORD-NONE-1", qty=10)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-NONE-1")

    router.register_and_route(cmd, tok)
    router.handle_execution_report(oid, make_report("ORD-NONE-1", "EXEC-N1", executed_qty=4))

    assert router.fsm.get_status(oid) == OrderStatus.PARTIAL
    assert router.get_executed_qty(oid) == 4
    assert router.is_execution_processed("EXEC-N1") is True
