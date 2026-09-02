"""tests/unit/test_startup_recovery.py

[D-13] Startup WAL 로드 및 Broker Recovery 플로우 검증 테스트 스위트.
- 테스트 1: 재시작 시 WAL 이벤트(ORDER_INTENT, BROKER_UNKNOWN, EXECUTION) FSM/수량/exec_id 복원 검증
- 테스트 2: 복원 후 동일 과거 exec_id 재수신 시 멱등성 중복 방어 검증
- 테스트 3: UNKNOWN 주문의 Broker get_order_status / get_open_orders 조회를 통한 ACCEPTED 복구 검증
- 테스트 4: Broker get_order_status를 통한 FILLED 상태 복구 및 정리 검증
- 테스트 5: Broker get_order_status를 통한 CANCELLED/REJECTED 복구 및 active_orders 정리 검증
- 테스트 6: Broker None/예외/불명확 응답 시 UNKNOWN 유지 및 신규 주문 차단 검증
- 테스트 7: TradingSystem.initialize()에서 Broker 연결 후 startup_recovery 자동 완결 검증
- 테스트 8: startup recovery 완료 전 run_loop 호출 시 안전 차단(RuntimeError) 검증
- 테스트 9: WAL 읽기 실패 시 부팅 차단 정책 검증
"""

import uuid
from unittest.mock import MagicMock
import pytest
from infra.wal_store import WalStore
from main import TradingSystem, BrokerMode
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


def make_cmd(client_id: str = "ORD-SU-01", qty: int = 10, price: float = 3.0) -> CanonicalOrderCommand:
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


def make_token(order_uuid: uuid.UUID, client_id: str = "ORD-SU-01") -> RiskApprovalToken:
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


class MockBrokerAdapter:
    """테스트용 Broker Adapter"""
    def __init__(self):
        self.status_map = {}
        self.open_orders_list = []
        self._connected = True

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def get_order_status(self, order_identifier: str = ""):
        return self.status_map.get(order_identifier)

    def get_open_orders(self):
        return self.open_orders_list

    def get_account_summary(self):
        from shared.contracts.canonical import CanonicalAccountSummary
        return CanonicalAccountSummary(
            account_id="ACC-TEST",
            total_balance=50_000_000.0,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            used_margin=0.0,
            free_margin=50_000_000.0,
        )

    def get_positions(self):
        return {}

    def send_order(self, order_command):
        from option_program.broker.broker_interface import BrokerOrderResponse
        return BrokerOrderResponse(
            success=True,
            status="ACCEPTED",
            client_order_id=getattr(order_command, "client_order_id", ""),
            broker_order_id=f"B-{getattr(order_command, 'client_order_id', '')}",
        )

    def poll_execution_reports(self):
        return []


@pytest.mark.asyncio
async def test_startup_wal_recovery_restores_state_and_exec_ids(tmp_path):
    """테스트 1 & 2: WAL 재생을 통한 상태 복원 및 동일 과거 exec_id 재수신 차단 검증."""
    wal_file = str(tmp_path / "startup_test.wal")
    wal_store = WalStore(log_path=wal_file)

    # 1. 1차 세션: 주문 생성 및 부분 체결 2회 기록
    router1 = OrderRouter(wal_store=wal_store)
    cmd = make_cmd("ORD-STARTUP-1", qty=10)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-STARTUP-1")
    router1.register_and_route(command=cmd, token=tok)

    rep1 = make_report(oid, "ORD-STARTUP-1", exec_id="EXEC-SU-1", exec_qty=3)
    router1.handle_execution_report(oid, rep1)

    rep2 = make_report(oid, "ORD-STARTUP-1", exec_id="EXEC-SU-2", exec_qty=4)
    router1.handle_execution_report(oid, rep2)

    assert router1.get_executed_qty(oid) == 7

    # 2. 2차 세션 (프로세스 재시작): OptionProgramRuntime의 startup_recovery 실행
    runtime2 = OptionProgramRuntime(wal_store=wal_store)
    broker = MockBrokerAdapter()
    broker.open_orders_list = [{
        "client_order_id": "ORD-STARTUP-1",
        "status": "PARTIAL",
        "executed_qty": 7,
    }]
    summary = runtime2.startup_recovery(broker_adapter=broker)

    assert summary["wal_events_count"] == 3  # ORDER_INTENT (1) + PARTIAL_EXECUTION (2)
    assert summary["recovery_completed"] is True
    assert runtime2.get_order_executed_qty("ORD-STARTUP-1") == 7
    assert runtime2.order_router.fsm.get_status(oid) == OrderStatus.PARTIAL

    # 3. 과거 exec_id 재수신 시 멱등성 차단
    ok_dup = runtime2.consume_execution_report(rep1)
    assert ok_dup is True
    assert runtime2.get_order_executed_qty("ORD-STARTUP-1") == 7


def test_startup_recovery_with_broker_order_status_open(tmp_path):
    """테스트 3: UNKNOWN 주문의 Broker get_order_status 조회를 통한 ACCEPTED 복구 검증."""
    wal_file = str(tmp_path / "startup_unk.wal")
    wal_store = WalStore(log_path=wal_file)
    router1 = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-UNK-SU", qty=5)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-UNK-SU")
    router1.register_and_route(command=cmd, token=tok)
    router1.mark_order_unknown("ORD-UNK-SU", reason="TIMEOUT_UNKNOWN")

    assert router1.has_unresolved_unknown_orders() is True

    # 재시작 후 Broker와 대사
    broker = MockBrokerAdapter()
    broker.status_map["ORD-UNK-SU"] = {
        "client_order_id": "ORD-UNK-SU",
        "broker_order_id": "BRK-SU-10",
        "status": "ACCEPTED",
        "executed_qty": 0,
    }

    runtime2 = OptionProgramRuntime(wal_store=wal_store)
    summary = runtime2.startup_recovery(broker_adapter=broker)

    assert summary["broker_recovery_summary"]["recovered"] == 1
    assert summary["has_unresolved_unknown"] is False
    assert runtime2.order_router.fsm.get_status(oid) == OrderStatus.ACCEPTED


def test_startup_recovery_with_broker_open_orders(tmp_path):
    """테스트 3-B: UNKNOWN 주문이 get_open_orders 목록을 통해 복구되는지 검증."""
    wal_file = str(tmp_path / "startup_open_ord.wal")
    wal_store = WalStore(log_path=wal_file)
    router1 = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-OPEN-SU", qty=10)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-OPEN-SU")
    router1.register_and_route(command=cmd, token=tok)
    router1.mark_order_unknown("ORD-OPEN-SU", reason="TIMEOUT_UNKNOWN")

    broker = MockBrokerAdapter()
    # status_map에는 없고 open_orders_list에만 있는 경우
    broker.open_orders_list = [{
        "client_order_id": "ORD-OPEN-SU",
        "broker_order_id": "BRK-OPEN-01",
        "status": "OPEN",
        "executed_qty": 0,
    }]

    runtime2 = OptionProgramRuntime(wal_store=wal_store)
    summary = runtime2.startup_recovery(broker_adapter=broker)

    assert summary["broker_recovery_summary"]["recovered"] == 1
    assert summary["has_unresolved_unknown"] is False
    assert runtime2.order_router.fsm.get_status(oid) == OrderStatus.ACCEPTED


def test_startup_recovery_terminal_states_cleanup(tmp_path):
    """테스트 4 & 5: Broker 조회를 통한 FILLED / CANCELLED / REJECTED 복구 및 정리 검증."""
    wal_file = str(tmp_path / "startup_term.wal")
    wal_store = WalStore(log_path=wal_file)
    router1 = OrderRouter(wal_store=wal_store)

    # 주문 1, 2, 3 등록 (정상 전송 상태)
    cmd1 = make_cmd("ORD-TERM-FILL", qty=5)
    oid1 = uuid.uuid4()
    tok1 = make_token(oid1, "ORD-TERM-FILL")
    router1.register_and_route(command=cmd1, token=tok1)

    cmd2 = make_cmd("ORD-TERM-CAN", qty=3)
    oid2 = uuid.uuid4()
    tok2 = make_token(oid2, "ORD-TERM-CAN")
    router1.register_and_route(command=cmd2, token=tok2)

    cmd3 = make_cmd("ORD-TERM-REJ", qty=2)
    oid3 = uuid.uuid4()
    tok3 = make_token(oid3, "ORD-TERM-REJ")
    router1.register_and_route(command=cmd3, token=tok3)

    # 타임아웃 발생으로 3개 주문 UNKNOWN 전환
    router1.mark_order_unknown("ORD-TERM-FILL")
    router1.mark_order_unknown("ORD-TERM-CAN")
    router1.mark_order_unknown("ORD-TERM-REJ")

    broker = MockBrokerAdapter()
    broker.status_map["ORD-TERM-FILL"] = {"status": "FILLED", "executed_qty": 5}
    broker.status_map["ORD-TERM-CAN"] = {"status": "CANCELLED", "executed_qty": 0}
    broker.status_map["ORD-TERM-REJ"] = {"status": "REJECTED", "executed_qty": 0}

    runtime2 = OptionProgramRuntime(wal_store=wal_store)
    summary = runtime2.startup_recovery(broker_adapter=broker)

    assert summary["broker_recovery_summary"]["recovered"] == 3
    assert runtime2.order_router.fsm.get_status(oid1) == OrderStatus.FILLED
    assert runtime2.order_router.fsm.get_status(oid2) == OrderStatus.CANCELLED
    assert runtime2.order_router.fsm.get_status(oid3) == OrderStatus.REJECTED
    assert oid1 not in runtime2.order_router._active_orders
    assert oid2 not in runtime2.order_router._active_orders
    assert oid3 not in runtime2.order_router._active_orders


def test_startup_recovery_unclear_maintains_unknown_and_blocks_trading(tmp_path):
    """테스트 6: Broker 응답 불명확 시 UNKNOWN 유지 및 신규 주문 차단 검증."""
    wal_file = str(tmp_path / "startup_unclear.wal")
    wal_store = WalStore(log_path=wal_file)
    router1 = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-UNCLEAR-SU", qty=5)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-UNCLEAR-SU")
    router1.register_and_route(command=cmd, token=tok)
    router1.mark_order_unknown("ORD-UNCLEAR-SU")

    broker = MockBrokerAdapter()
    broker.status_map["ORD-UNCLEAR-SU"] = None  # 불명확 응답

    runtime2 = OptionProgramRuntime(wal_store=wal_store)
    summary = runtime2.startup_recovery(broker_adapter=broker)

    assert summary["broker_recovery_summary"]["remained_unknown"] == 1
    assert summary["has_unresolved_unknown"] is True
    assert runtime2.has_unresolved_unknown_orders() is True
    assert runtime2.order_router.fsm.get_status(oid) == OrderStatus.UNKNOWN


@pytest.mark.asyncio
async def test_trading_system_initialize_executes_startup_recovery(tmp_path):
    """테스트 7: TradingSystem.initialize()에서 Broker connect 후 startup_recovery 자동 실행 확인."""
    wal_file = str(tmp_path / "system_init.wal")
    wal_store = WalStore(log_path=wal_file)

    ts = TradingSystem(config={
        "mode": "PAPER",
        "wal_store": wal_store,
        "wal_log_path": wal_file,
    })
    await ts.initialize()

    assert ts.broker is not None
    assert ts.broker.is_connected() is True
    assert ts.op_runtime is not None
    assert ts.op_runtime.recovery_completed is True


@pytest.mark.asyncio
async def test_run_loop_aborts_if_recovery_not_completed():
    """테스트 8: startup recovery 완료 전 run_loop 호출 시 안전 차단(RuntimeError) 검증."""
    ts = TradingSystem(config={"mode": "PAPER"})
    await ts.initialize()
    # 강제로 recovery_completed를 False로 해제
    ts.op_runtime.recovery_completed = False

    with pytest.raises(RuntimeError, match="startup recovery must be completed before starting run_loop"):
        await ts.run_loop(max_ticks=1)


def test_startup_wal_failure_aborts_safely():
    """테스트 9: WAL 읽기 중 예외 발생 시 에러 전파 및 안전 정책 검증."""
    mock_wal = MagicMock()
    mock_wal.load_history_sync.side_effect = IOError("Corrupted disk block")

    runtime = OptionProgramRuntime(wal_store=mock_wal)
    broker = MockBrokerAdapter()

    with pytest.raises(RuntimeError, match="Startup WAL load failed"):
        runtime.startup_recovery(broker_adapter=broker)

    assert runtime.recovery_completed is False


@pytest.mark.asyncio
async def test_10_repeated_startup_recovery_lifecycle_and_run_loop_blocking(tmp_path):
    """테스트 10: 동일 Runtime 기준 반복 복구 라이프사이클 (성공 -> 실패 -> 거래차단 -> 재성공 -> 멱등성) 검증."""
    wal_file = str(tmp_path / "repeated_rec.wal")
    wal_store = WalStore(log_path=wal_file)

    # 초기 주문 생성 및 WAL 영속화
    router0 = OrderRouter(wal_store=wal_store)
    cmd = make_cmd("ORD-REPEAT-1", qty=10, price=2.5)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-REPEAT-1")
    router0.register_and_route(cmd, tok)

    # 체결 이벤트 1회 영속화
    rep = make_report(oid, "ORD-REPEAT-1", "EXEC-REP-01", exec_qty=4, price=2.5)
    router0.handle_execution_report(oid, rep)

    broker = MockBrokerAdapter()
    broker.status_map["ORD-REPEAT-1"] = {"status": "PARTIAL", "executed_qty": 4}

    # 동일 Runtime 인스턴스 생성
    runtime = OptionProgramRuntime(wal_store=wal_store)

    # -------------------------------------------------------------
    # A. 1차 Recovery 성공 -> recovery_completed is True
    # -------------------------------------------------------------
    summary1 = runtime.startup_recovery(broker_adapter=broker)
    assert summary1["recovery_completed"] is True
    assert runtime.recovery_completed is True
    assert runtime.order_router.get_executed_qty(oid) == 4
    assert runtime.order_router.fsm.get_status(oid) == OrderStatus.PARTIAL

    # -------------------------------------------------------------
    # B. 2차 Recovery에서 실패 주입 -> 예외 발생 및 recovery_completed is False
    # -------------------------------------------------------------
    failing_wal = MagicMock()
    failing_wal.load_history_sync.side_effect = IOError("Disk I/O error during repeated recovery")
    runtime.wal_store = failing_wal

    with pytest.raises(RuntimeError, match="Startup WAL load failed"):
        runtime.startup_recovery(broker_adapter=broker)

    # [핵심 검증] 이전 True가 남지 않고 반드시 False로 리셋되어야 함
    assert runtime.recovery_completed is False

    # -------------------------------------------------------------
    # C. 실패 상태에서 run_loop 호출 시 거래 차단 검증 (Transport 0건)
    # -------------------------------------------------------------
    ts = TradingSystem(config={"mode": "PAPER"})
    await ts.initialize()
    ts.op_runtime = runtime
    ts.broker = broker

    with pytest.raises(RuntimeError, match="startup recovery must be completed before starting run_loop"):
        await ts.run_loop(max_ticks=1)

    # -------------------------------------------------------------
    # D. 실패 원인 제거 후 3차 Recovery 재성공 -> recovery_completed is True
    # -------------------------------------------------------------
    runtime.wal_store = wal_store
    summary3 = runtime.startup_recovery(broker_adapter=broker)

    assert summary3["recovery_completed"] is True
    assert runtime.recovery_completed is True

    # -------------------------------------------------------------
    # E. 반복 상태 멱등성 검증: 체결 수량 중복 증가 없음 & FSM 일관성 유지
    # -------------------------------------------------------------
    assert runtime.order_router.get_executed_qty(oid) == 4
    assert runtime.order_router.fsm.get_status(oid) == OrderStatus.PARTIAL


@pytest.mark.asyncio
async def test_11_long_running_wal_accumulation_and_idempotent_recovery(tmp_path):
    """테스트 11: [10단계-5] 장시간 운영 모사 대량 WAL 누적, 정확한 복원, 반복 멱등성 및 런타임 안전 인터록 검증."""
    wal_file = str(tmp_path / "long_running.wal")
    wal_store = WalStore(log_path=wal_file)

    # 1. 1차 세션: 2개 주문에 대해 100건의 고유 체결 이벤트 대량 생성 및 WAL 영속화
    router0 = OrderRouter(wal_store=wal_store)

    # 주문 1: Qty 100 (50회 부분 체결 -> 누적 50, PARTIAL)
    cmd1 = make_cmd("ORD-LONG-01", qty=100, price=3.5)
    oid1 = uuid.uuid4()
    tok1 = make_token(oid1, "ORD-LONG-01")
    router0.register_and_route(cmd1, tok1)

    for i in range(1, 51):
        rep = make_report(oid1, "ORD-LONG-01", f"EXEC-LONG-1-{i:04d}", exec_qty=1, price=3.5)
        router0.handle_execution_report(oid1, rep)

    # 주문 2: Qty 50 (50회 체결 -> 누적 50, FILLED)
    cmd2 = make_cmd("ORD-LONG-02", qty=50, price=2.0)
    oid2 = uuid.uuid4()
    tok2 = make_token(oid2, "ORD-LONG-02")
    router0.register_and_route(cmd2, tok2)

    for i in range(1, 51):
        rep = make_report(oid2, "ORD-LONG-02", f"EXEC-LONG-2-{i:04d}", exec_qty=1, price=2.0)
        router0.handle_execution_report(oid2, rep)

    assert router0.get_executed_qty(oid1) == 50
    assert router0.fsm.get_status(oid1) == OrderStatus.PARTIAL
    assert router0.get_executed_qty(oid2) == 50
    assert router0.fsm.get_status(oid2) == OrderStatus.FILLED
    assert len(router0._processed_exec_ids) == 100

    # 2. 신규 세션(새 Runtime 인스턴스)에서 장시간 누적 WAL 로드 및 Recovery 수행
    runtime_fresh = OptionProgramRuntime(wal_store=wal_store)
    broker = MockBrokerAdapter()
    broker.open_orders_list = [{
        "client_order_id": "ORD-LONG-01",
        "status": "PARTIAL",
        "executed_qty": 50,
    }]
    broker.status_map["ORD-LONG-02"] = {"status": "FILLED", "executed_qty": 50}

    summary1 = runtime_fresh.startup_recovery(broker_adapter=broker)

    # 3. 1차 복구 결과 검증
    # WAL 이벤트 수: ORDER_INTENT (2건) + PARTIAL/FILLED_EXECUTION (100건) = 102건
    assert summary1["wal_events_count"] == 102
    assert summary1["recovery_completed"] is True
    assert runtime_fresh.recovery_completed is True
    assert runtime_fresh.get_order_executed_qty("ORD-LONG-01") == 50
    assert runtime_fresh.order_router.fsm.get_status(oid1) == OrderStatus.PARTIAL
    assert runtime_fresh.get_order_executed_qty("ORD-LONG-02") == 50
    assert runtime_fresh.order_router.fsm.get_status(oid2) == OrderStatus.FILLED
    assert len(runtime_fresh.order_router._processed_exec_ids) == 100

    # 4. 동일 Runtime에서 2차 Recovery 재수행 (반복 복구 멱등성 검증)
    summary2 = runtime_fresh.startup_recovery(broker_adapter=broker)
    assert summary2["recovery_completed"] is True
    assert runtime_fresh.recovery_completed is True
    assert runtime_fresh.get_order_executed_qty("ORD-LONG-01") == 50
    assert runtime_fresh.order_router.fsm.get_status(oid1) == OrderStatus.PARTIAL
    assert runtime_fresh.get_order_executed_qty("ORD-LONG-02") == 50
    assert runtime_fresh.order_router.fsm.get_status(oid2) == OrderStatus.FILLED
    assert len(runtime_fresh.order_router._processed_exec_ids) == 100

    # 5. 과거 체결 이벤트 재유입 시 멱등성 방어 검증 (중복 누적 0건)
    dup_rep = make_report(oid1, "ORD-LONG-01", "EXEC-LONG-1-0025", exec_qty=1, price=3.5)
    ok_dup = runtime_fresh.consume_execution_report(dup_rep)
    assert ok_dup is True
    assert runtime_fresh.get_order_executed_qty("ORD-LONG-01") == 50
    assert len(runtime_fresh.order_router._processed_exec_ids) == 100

    # 6. Recovery 완료 후 TradingSystem 안전 인터록 검증
    ts = TradingSystem(config={"mode": "PAPER"})
    await ts.initialize()
    ts.op_runtime = runtime_fresh
    ts.broker = broker

    # recovery_completed=True 이므로 run_loop 진입 가능 확인 (1틱 정상 실행 검증)
    await ts.run_loop(max_ticks=1)
    assert ts.last_tick is not None
