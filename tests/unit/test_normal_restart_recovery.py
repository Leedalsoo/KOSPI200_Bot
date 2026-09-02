"""[10단계 — 정상 복구] WAL/기존 영속 상태 기반 OMS/FSM 상태 복원 및 정상 복구 완료/차단 전수 검증."""
import os
import time
import uuid
import pytest
from typing import Dict, Any, List, Optional

from shared.contracts.canonical import (
    CanonicalOrderCommand,
    CanonicalOrderSide,
    CanonicalAssetType,
    CanonicalOptionType,
    CanonicalExecutionReport,
)
from shared.core.contracts import OrderStatus, RiskApprovalToken
from infra.wal_store import WalStore
from option_program.orders.order_router import OrderRouter
from option_program.runtime.program_runtime import OptionProgramRuntime
from virtual_securities_firm.account.paper_account import PaperTradingAccount
from virtual_securities_firm.recovery.state_recovery import StateRecoveryEngine
from main import TradingSystem, BrokerMode


# ==============================================================================
# Helper Functions and Mock Broker Classes
# ==============================================================================


def make_test_cmd(
    client_id: str = "ORD-TEST-01",
    qty: int = 10,
    price: float = 3.0,
    side: CanonicalOrderSide = CanonicalOrderSide.BUY,
    track_id: str = "Track1",
) -> CanonicalOrderCommand:
    return CanonicalOrderCommand(
        client_order_id=client_id,
        track_id=track_id,
        asset_type=CanonicalAssetType.OPTION,
        side=side,
        qty=qty,
        price=price,
        symbol="201V3350",
        option_type=CanonicalOptionType.CALL,
        strike=350.0,
    )



def make_test_token(order_uuid: uuid.UUID, client_id: str = "ORD-TEST-01", track_id: str = "Track1") -> RiskApprovalToken:
    return RiskApprovalToken(
        order_id=order_uuid,
        timestamp_ns=1000000,
        signature=f"SIG-RISK-APPROVED-{track_id}-{client_id}",
    )


def make_test_report(
    order_id: uuid.UUID,
    client_id: str,
    exec_id: str,
    exec_qty: int,
    price: float = 3.0,
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
        timestamp="2026-08-23 10:00:00",
    )


class MockSuccessBroker:
    def __init__(self, open_orders: Optional[List[Dict[str, Any]]] = None):
        self._open_orders = open_orders or []

    def get_open_orders(self) -> List[Dict[str, Any]]:
        return self._open_orders

    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        return {"status": "FILLED", "executed_qty": 5}


class MockFailingBroker:
    def get_open_orders(self) -> List[Dict[str, Any]]:
        raise ConnectionResetError("Broker network disconnect during recovery")

    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        raise ConnectionResetError("Broker network disconnect")


class MockUncertainBroker:
    def get_open_orders(self) -> List[Dict[str, Any]]:
        return []

    def get_order_status(self, order_id: str) -> Optional[Dict[str, Any]]:
        return None  # Status uncertain -> forces UNKNOWN


# ==============================================================================
# 12대 정상 복구 필수 테스트
# ==============================================================================


def test_1_empty_wal_normal_startup(tmp_path):
    """1. 빈 WAL 정상 시작: recovery_completed=True, 0건 복원, 미해결 UNKNOWN 0건."""
    wal_file = str(tmp_path / "empty_orders.wal")
    wal_store = WalStore(log_path=wal_file)
    runtime = OptionProgramRuntime(wal_store=wal_store)

    summary = runtime.startup_recovery(broker_adapter=None)

    assert summary["wal_events_count"] == 0
    assert summary["wal_recovered_count"] == 0
    assert summary["unresolved_unknown_count"] == 0
    assert summary["has_unresolved_unknown"] is False
    assert summary["recovery_completed"] is True
    assert runtime.recovery_completed is True


def test_2_order_intent_only_restart_recovery(tmp_path):
    """2. ORDER_INTENT 단독 재시작 -> SENT/active/client mapping 복원."""
    wal_file = str(tmp_path / "intent_only.wal")
    wal_store = WalStore(log_path=wal_file)

    order_uuid = str(uuid.uuid4())
    client_id = "ORD-INTENT-001"
    data = {
        "order_id": order_uuid,
        "client_order_id": client_id,
        "broker_order_id": "BRK-001",
        "side": "BUY",
        "qty": 10,
        "price": 2.50,
        "symbol": "201V3350",
        "timestamp": time.time(),
    }
    wal_store.save_event_sync("ORDER_INTENT", data)

    new_runtime = OptionProgramRuntime(wal_store=wal_store)
    summary = new_runtime.startup_recovery()

    assert summary["wal_recovered_count"] == 1
    assert summary["recovery_completed"] is True

    parsed_uuid = uuid.UUID(order_uuid)
    assert new_runtime.order_router.fsm.get_status(parsed_uuid) == OrderStatus.SENT
    assert parsed_uuid in new_runtime.order_router._active_orders
    assert new_runtime.order_router.get_broker_order_id(client_id) == "BRK-001"
    assert new_runtime.order_router.get_broker_order_id(parsed_uuid) == "BRK-001"


def test_3_order_intent_and_partial_execution_recovery(tmp_path):
    """3. ORDER_INTENT + PARTIAL_EXECUTION -> PARTIAL 및 cumulative qty 복원."""
    wal_file = str(tmp_path / "partial_exec.wal")
    wal_store = WalStore(log_path=wal_file)

    order_uuid = str(uuid.uuid4())
    client_id = "ORD-PARTIAL-001"
    wal_store.save_event_sync("ORDER_INTENT", {
        "order_id": order_uuid,
        "client_order_id": client_id,
        "side": "BUY",
        "qty": 10,
        "price": 3.0,
        "symbol": "201V3350",
    })
    wal_store.save_event_sync("PARTIAL_EXECUTION", {
        "order_id": order_uuid,
        "client_order_id": client_id,
        "exec_id": "EXEC-PART-01",
        "cum_executed_qty": 4,
        "status": "PARTIAL",
    })

    new_runtime = OptionProgramRuntime(wal_store=wal_store)
    summary = new_runtime.startup_recovery()

    assert summary["wal_recovered_count"] == 2
    assert summary["recovery_completed"] is True

    parsed_uuid = uuid.UUID(order_uuid)
    assert new_runtime.order_router.fsm.get_status(parsed_uuid) == OrderStatus.PARTIAL
    assert new_runtime.order_router.get_executed_qty(parsed_uuid) == 4
    assert new_runtime.order_router.get_executed_qty(client_id) == 4
    assert parsed_uuid in new_runtime.order_router._active_orders
    assert new_runtime.order_router.is_execution_processed("EXEC-PART-01") is True


def test_4_order_intent_and_filled_execution_recovery(tmp_path):
    """4. ORDER_INTENT + FILLED_EXECUTION -> FILLED 및 active 정리 복원."""
    wal_file = str(tmp_path / "filled_exec.wal")
    wal_store = WalStore(log_path=wal_file)

    order_uuid = str(uuid.uuid4())
    client_id = "ORD-FILLED-001"
    wal_store.save_event_sync("ORDER_INTENT", {
        "order_id": order_uuid,
        "client_order_id": client_id,
        "side": "SELL",
        "qty": 5,
        "price": 4.5,
        "symbol": "201V3350",
    })
    wal_store.save_event_sync("FILLED_EXECUTION", {
        "order_id": order_uuid,
        "client_order_id": client_id,
        "exec_id": "EXEC-FULL-01",
        "cum_executed_qty": 5,
        "status": "FILLED",
    })

    new_runtime = OptionProgramRuntime(wal_store=wal_store)
    summary = new_runtime.startup_recovery()

    assert summary["wal_recovered_count"] == 2
    assert summary["recovery_completed"] is True

    parsed_uuid = uuid.UUID(order_uuid)
    assert new_runtime.order_router.fsm.get_status(parsed_uuid) == OrderStatus.FILLED
    assert new_runtime.order_router.get_executed_qty(parsed_uuid) == 5
    assert parsed_uuid not in new_runtime.order_router._active_orders
    assert new_runtime.order_router.is_execution_processed("EXEC-FULL-01") is True


def test_5_duplicate_exec_id_idempotency_recovery(tmp_path):
    """5. exec_id 중복 WAL -> 멱등성 유지 및 누적 체결 수량 안정성."""
    wal_file = str(tmp_path / "dup_exec.wal")
    wal_store = WalStore(log_path=wal_file)

    order_uuid = str(uuid.uuid4())
    client_id = "ORD-DUP-001"
    wal_store.save_event_sync("ORDER_INTENT", {
        "order_id": order_uuid, "client_order_id": client_id, "qty": 10, "price": 2.0
    })
    # 동일한 exec_id의 체결 이벤트 2건
    for _ in range(2):
        wal_store.save_event_sync("PARTIAL_EXECUTION", {
            "order_id": order_uuid,
            "client_order_id": client_id,
            "exec_id": "EXEC-ID-DUP-999",
            "cum_executed_qty": 3,
            "status": "PARTIAL",
        })

    new_runtime = OptionProgramRuntime(wal_store=wal_store)
    new_runtime.startup_recovery()

    parsed_uuid = uuid.UUID(order_uuid)
    assert new_runtime.order_router.is_execution_processed("EXEC-ID-DUP-999") is True
    assert new_runtime.order_router.get_executed_qty(parsed_uuid) == 3


def test_6_unknown_to_unknown_recovered_lifecycle(tmp_path):
    """6. UNKNOWN -> UNKNOWN_RECOVERED -> 최종 상태 복원."""
    wal_file = str(tmp_path / "unknown_recovered.wal")
    wal_store = WalStore(log_path=wal_file)

    order_uuid = str(uuid.uuid4())
    client_id = "ORD-UNK-REC-01"
    wal_store.save_event_sync("ORDER_INTENT", {
        "order_id": order_uuid, "client_order_id": client_id, "qty": 8, "price": 3.0
    })
    wal_store.save_event_sync("BROKER_UNKNOWN", {
        "order_id": order_uuid, "client_order_id": client_id, "reason": "TIMEOUT_UNKNOWN"
    })
    wal_store.save_event_sync("UNKNOWN_RECOVERED", {
        "order_id": order_uuid,
        "client_order_id": client_id,
        "recovered_status": "FILLED",
    })

    new_runtime = OptionProgramRuntime(wal_store=wal_store)
    summary = new_runtime.startup_recovery()

    parsed_uuid = uuid.UUID(order_uuid)
    assert new_runtime.order_router.fsm.get_status(parsed_uuid) == OrderStatus.FILLED
    assert parsed_uuid not in new_runtime.order_router._unknown_orders
    assert parsed_uuid not in new_runtime.order_router._active_orders
    assert summary["unresolved_unknown_count"] == 0
    assert summary["recovery_completed"] is True


def test_7_corrupt_wal_lines_mixed_recovery(tmp_path):
    """7. 손상 WAL line + 유효 WAL line 혼합: 유효 이벤트 복원 및 안전 완료."""
    wal_file = str(tmp_path / "corrupt_mixed.wal")

    order_uuid = str(uuid.uuid4())
    valid_line_1 = f'{{"event_type": "ORDER_INTENT", "data": {{"order_id": "{order_uuid}", "client_order_id": "ORD-VALID-01", "qty": 5, "price": 2.0}}}}\n'
    corrupt_line_1 = '{"event_type": "CORRUPT_JSON_DATA", INVALID_JSON...\n'
    corrupt_line_2 = 'NOT_EVEN_JSON_LINE\n'
    valid_line_2 = f'{{"event_type": "PARTIAL_EXECUTION", "data": {{"order_id": "{order_uuid}", "client_order_id": "ORD-VALID-01", "exec_id": "EX-01", "cum_executed_qty": 2, "status": "PARTIAL"}}}}\n'

    with open(wal_file, "w", encoding="utf-8") as f:
        f.write(valid_line_1)
        f.write(corrupt_line_1)
        f.write(corrupt_line_2)
        f.write(valid_line_2)

    wal_store = WalStore(log_path=wal_file)
    new_runtime = OptionProgramRuntime(wal_store=wal_store)
    summary = new_runtime.startup_recovery()

    assert summary["wal_events_count"] == 2  # 손상 라인 2개 건너뜀
    assert summary["wal_recovered_count"] == 2
    assert summary["recovery_completed"] is True

    parsed_uuid = uuid.UUID(order_uuid)
    assert new_runtime.order_router.fsm.get_status(parsed_uuid) == OrderStatus.PARTIAL
    assert new_runtime.order_router.get_executed_qty(parsed_uuid) == 2


def test_8_broker_reconciliation_success_integration(tmp_path):
    """8. Broker reconciliation 성공 시 대사 정상 완료 및 recovery_completed=True."""
    wal_file = str(tmp_path / "recon_success.wal")
    wal_store = WalStore(log_path=wal_file)

    order_uuid = str(uuid.uuid4())
    client_id = "ORD-RECON-SUCCESS"
    wal_store.save_event_sync("ORDER_INTENT", {
        "order_id": order_uuid, "client_order_id": client_id, "qty": 5, "price": 2.5
    })

    # Broker는 이 주문이 Broker 상에서 ACCEPTED 상태임을 보고
    broker = MockSuccessBroker(open_orders=[{"client_order_id": client_id, "status": "ACCEPTED", "executed_qty": 0}])

    new_runtime = OptionProgramRuntime(wal_store=wal_store)
    summary = new_runtime.startup_recovery(broker_adapter=broker)

    assert summary["recovery_completed"] is True
    assert summary["reconciliation_summary"]["status"] == "COMPLETED"
    parsed_uuid = uuid.UUID(order_uuid)
    assert new_runtime.order_router.fsm.get_status(parsed_uuid) == OrderStatus.ACCEPTED


def test_9_broker_reconciliation_failure_blocks_recovery(tmp_path):
    """9. Broker reconciliation 실패/불확실 -> recovery 미완료 및 예외 발생 부팅 차단."""
    wal_file = str(tmp_path / "recon_fail.wal")
    wal_store = WalStore(log_path=wal_file)

    order_uuid = str(uuid.uuid4())
    client_id = "ORD-FAIL-01"
    wal_store.save_event_sync("ORDER_INTENT", {
        "order_id": order_uuid, "client_order_id": client_id, "qty": 5, "price": 2.5
    })

    # 1. Broker 대사 실패(status == FAILED) 시 RuntimeError 발생 검증
    broker_failing = MockFailingBroker()
    new_runtime = OptionProgramRuntime(wal_store=wal_store)
    with pytest.raises(RuntimeError) as exc_info:
        new_runtime.startup_recovery(broker_adapter=broker_failing)
    assert "Startup broker reconciliation failed" in str(exc_info.value)

    # 2. Broker 상태 불확실로 UNKNOWN 주문이 잔존하는 경우 안전 인터록 활성화 검증
    broker_uncertain = MockUncertainBroker()
    new_runtime_2 = OptionProgramRuntime(wal_store=wal_store)
    summary_2 = new_runtime_2.startup_recovery(broker_adapter=broker_uncertain)

    assert summary_2["has_unresolved_unknown"] is True
    assert new_runtime_2.order_router.has_unresolved_unknown_orders() is True
    assert new_runtime_2.has_unresolved_unknown_orders() is True


@pytest.mark.asyncio
async def test_10_run_loop_blocked_before_recovery(tmp_path):
    """10. recovery 전 run_loop() 호출 차단 검증."""
    system = TradingSystem(config={
        "wal_log_path": str(tmp_path / "orders.wal"),
        "broker_mode": "PAPER"
    })

    # 초기화 전 상태에서 run_loop 실행 시도
    with pytest.raises(RuntimeError) as exc_info:
        await system.run_loop(max_ticks=1)
    assert "TradingSystem must be initialized before run_loop" in str(exc_info.value)

    # op_runtime은 있으나 recovery_completed=False인 상태 시뮬레이션
    system.op_runtime = OptionProgramRuntime()
    system.op_runtime.recovery_completed = False
    system.vms = True
    system.broker = True

    with pytest.raises(RuntimeError) as exc_info2:
        await system.run_loop(max_ticks=1)
    assert "startup recovery must be completed before starting run_loop" in str(exc_info2.value)


def test_11_restart_oms_state_equivalence(tmp_path):
    """11. 재시작 전/후 핵심 OMS 상태 동등성 검증 (FSM, active orders, executed qty, mappings 100% 일치)."""
    wal_file = str(tmp_path / "equivalence.wal")
    wal_store = WalStore(log_path=wal_file)

    # 이전 실행 (Run 1)
    runtime_1 = OptionProgramRuntime(wal_store=wal_store)
    router_1 = runtime_1.order_router

    cmd1 = make_test_cmd("ORD-EQ-01", qty=10, price=3.5)
    uid1 = uuid.uuid4()
    tok1 = make_test_token(uid1, "ORD-EQ-01", track_id="Track1")
    router_1.register_and_route(command=cmd1, token=tok1)
    router_1.register_broker_order_id(uid1, "BRK-EQ-01")
    rep1 = make_test_report(uid1, "ORD-EQ-01", exec_id="EX-EQ-01", exec_qty=4)
    router_1.handle_execution_report(uid1, rep1)

    cmd2 = make_test_cmd("ORD-EQ-02", qty=5, price=2.0, side=CanonicalOrderSide.SELL, track_id="Track2")
    uid2 = uuid.uuid4()
    tok2 = make_test_token(uid2, "ORD-EQ-02", track_id="Track2")
    router_1.register_and_route(command=cmd2, token=tok2)
    rep2 = make_test_report(uid2, "ORD-EQ-02", exec_id="EX-EQ-02", exec_qty=5)
    router_1.handle_execution_report(uid2, rep2)

    # 상태 기록 확인
    r1_status_1 = router_1.fsm.get_status(uid1)
    r1_qty_1 = router_1.get_executed_qty(uid1)
    r1_active_count = len(router_1._active_orders)

    # 신규 인스턴스 재시작 (Run 2)
    runtime_2 = OptionProgramRuntime(wal_store=wal_store)
    summary = runtime_2.startup_recovery()

    router_2 = runtime_2.order_router
    assert summary["recovery_completed"] is True
    assert router_2.fsm.get_status(uid1) == r1_status_1 == OrderStatus.PARTIAL
    assert router_2.get_executed_qty(uid1) == r1_qty_1 == 4
    assert router_2.fsm.get_status(uid2) == OrderStatus.FILLED
    assert router_2.get_executed_qty(uid2) == 5
    assert len(router_2._active_orders) == r1_active_count == 1
    assert uid1 in router_2._active_orders
    assert uid2 not in router_2._active_orders
    assert router_2.is_execution_processed("EX-EQ-01") is True
    assert router_2.is_execution_processed("EX-EQ-02") is True


def test_12_state_recovery_engine_snapshot_integration():
    """12. Account/Position/Ledger snapshot 복구 엔진 무결성 및 연결 검증."""
    account = PaperTradingAccount(initial_capital=50000000.0)
    engine = StateRecoveryEngine(account=account)

    # 1. 상태 변경: 잔고 및 포지션 생성
    account.balance = 48000000.0
    account.used_margin = 15000000.0
    account.free_margin = 33000000.0
    account.realized_pnl = 1200000.0
    account.positions = {
        "201V3350": {"symbol": "201V3350", "qty": 5, "entry_price": 3.50, "current_price": 3.80}
    }

    # 2. 스냅샷 생성
    snap = engine.create_snapshot(sequence_id=101, metrics={"trade_count": 12})
    assert snap["total_balance"] == 49200000.0
    assert snap["sequence_id"] == 101

    # 3. 다른 계좌 인스턴스로 복원
    new_account = PaperTradingAccount(initial_capital=10000000.0)
    new_engine = StateRecoveryEngine(account=new_account)
    target_metrics: Dict[str, Any] = {}
    success = new_engine.restore_from_snapshot(snap, target_metrics=target_metrics)

    assert success is True
    assert new_account.balance == 48000000.0
    assert new_account.used_margin == 15000000.0
    assert new_account.free_margin == 33000000.0
    assert new_account.realized_pnl == 1200000.0
    assert "201V3350" in new_account.positions
    assert new_account.positions["201V3350"]["qty"] == 5
    assert target_metrics["trade_count"] == 12
