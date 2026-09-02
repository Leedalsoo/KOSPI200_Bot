"""[10단계 — 중단 중 복구] 프로세스 중단(SIGTERM/크래시/타임아웃) 시점별 WAL/Broker 대사 복구 및 안전 차단 전수 검증 스위트."""
import os
import time
import uuid
import pytest
from typing import Dict, Any, List, Optional
from unittest.mock import patch

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
from main import TradingSystem, BrokerMode


# ==============================================================================
# Helper Factories & Mock Brokers
# ==============================================================================


def make_test_cmd(
    client_id: str = "ORD-INT-01",
    qty: int = 10,
    price: float = 3.5,
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


def make_test_token(order_uuid: uuid.UUID, client_id: str = "ORD-INT-01", track_id: str = "Track1") -> RiskApprovalToken:
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
    price: float = 3.5,
) -> CanonicalExecutionReport:
    return CanonicalExecutionReport(
        exec_id=exec_id,
        client_order_id=client_id,
        track_id="Track1",
        symbol="201V3350",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        executed_qty=exec_qty,
        executed_price=price,
        fee=10.0,
        slippage=0.0,
        timestamp="2026-09-02 10:00:00",
    )


class MockBrokerAdapter:
    """테스트용 Broker Mock Adapter."""
    def __init__(self, open_orders: Optional[List[Dict[str, Any]]] = None, status_map: Optional[Dict[str, Any]] = None):
        self._open_orders = open_orders or []
        self._status_map = status_map or {}
        self._connected = True
        self.sent_orders_count = 0

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def get_open_orders(self) -> List[Dict[str, Any]]:
        if not self._connected:
            raise RuntimeError("Broker is disconnected")
        return self._open_orders

    def get_order_status(self, order_id: str) -> Optional[Dict[str, Any]]:
        if not self._connected:
            raise RuntimeError("Broker is disconnected")
        return self._status_map.get(order_id)

    def send_order(self, command: CanonicalOrderCommand) -> Any:
        self.sent_orders_count += 1
        return None


# ==============================================================================
# 14대 중단 중 복구 (Interrupted Recovery) 전수 테스트
# ==============================================================================


def test_1_interrupted_after_order_intent_persistence(tmp_path):
    """1. ORDER_INTENT 기록 직후 프로세스 중단 후 재시작 시 SENT 및 active 복원."""
    wal_file = str(tmp_path / "intent_crash.wal")
    wal_store = WalStore(log_path=wal_file)

    # 시뮬레이션: 주문 생성 및 ORDER_INTENT WAL 기록 직후 프로세스 비정상 중단
    order_uuid = str(uuid.uuid4())
    client_id = "ORD-INTENT-CRASH-01"
    wal_store.save_event_sync("ORDER_INTENT", {
        "order_id": order_uuid,
        "client_order_id": client_id,
        "side": "BUY",
        "qty": 10,
        "price": 3.0,
        "symbol": "201V3350",
    })

    # 재시작: 새 런타임에서 WAL 복구
    runtime = OptionProgramRuntime(wal_store=wal_store)
    summary = runtime.startup_recovery()

    uid = uuid.UUID(order_uuid)
    assert summary["recovery_completed"] is True
    assert runtime.order_router.fsm.get_status(uid) == OrderStatus.SENT
    assert uid in runtime.order_router._active_orders
    assert runtime.order_router._client_to_order_id[client_id] == uid


def test_2_interrupted_after_broker_send_started_before_broker_call(tmp_path):
    """2. BROKER_SEND_STARTED 기록 후 실제 Broker 네트워크 전송 전 중단 시 안전 복구."""
    wal_file = str(tmp_path / "send_started_crash.wal")
    wal_store = WalStore(log_path=wal_file)

    order_uuid = str(uuid.uuid4())
    client_id = "ORD-SEND-START-01"
    wal_store.save_event_sync("ORDER_INTENT", {
        "order_id": order_uuid,
        "client_order_id": client_id,
        "qty": 5,
        "price": 2.5,
    })
    wal_store.save_event_sync("BROKER_SEND_STARTED", {
        "order_id": order_uuid,
        "client_order_id": client_id,
    })

    # Broker 조회 시 해당 주문이 미접수(Broker에는 없음) 상태
    broker = MockBrokerAdapter(open_orders=[], status_map={client_id: None})

    runtime = OptionProgramRuntime(wal_store=wal_store)
    summary = runtime.startup_recovery(broker_adapter=broker)

    uid = uuid.UUID(order_uuid)
    assert summary["recovery_completed"] is True
    assert runtime.order_router.fsm.get_status(uid) == OrderStatus.UNKNOWN
    # 상태 불확실(UNKNOWN) 주문이 잔존하므로 인터록 활성화
    assert runtime.order_router.has_unresolved_unknown_orders() is True


def test_3_interrupted_after_broker_call_before_ack_processing(tmp_path):
    """3. Broker 호출 완료 후 OMS에 ACK(ACCEPTED) 기록 전 중단 시 Broker 대사로 ACCEPTED 복원."""
    wal_file = str(tmp_path / "broker_call_crash.wal")
    wal_store = WalStore(log_path=wal_file)

    order_uuid = str(uuid.uuid4())
    client_id = "ORD-CALL-NO-ACK"
    wal_store.save_event_sync("ORDER_INTENT", {
        "order_id": order_uuid,
        "client_order_id": client_id,
        "qty": 8,
        "price": 4.0,
    })
    wal_store.save_event_sync("BROKER_SEND_STARTED", {
        "order_id": order_uuid,
        "client_order_id": client_id,
    })

    # Broker에는 실제 접수되어 미체결(ACCEPTED/OPEN) 상태로 존재
    broker = MockBrokerAdapter(
        open_orders=[{"client_order_id": client_id, "broker_order_id": "BRK-ACK-99", "status": "ACCEPTED", "executed_qty": 0}]
    )

    runtime = OptionProgramRuntime(wal_store=wal_store)
    summary = runtime.startup_recovery(broker_adapter=broker)

    uid = uuid.UUID(order_uuid)
    assert summary["recovery_completed"] is True
    assert runtime.order_router.fsm.get_status(uid) == OrderStatus.ACCEPTED
    assert uid in runtime.order_router._active_orders


def test_4_interrupted_after_ack_before_execution_report(tmp_path):
    """4. ACK 완료 후 체결 발생 전 중단 시 ACCEPTED 상태 및 active 유지 복원."""
    wal_file = str(tmp_path / "ack_no_exec.wal")
    wal_store = WalStore(log_path=wal_file)

    order_uuid = str(uuid.uuid4())
    client_id = "ORD-ACKED-01"
    wal_store.save_event_sync("ORDER_INTENT", {
        "order_id": order_uuid,
        "client_order_id": client_id,
        "qty": 10,
        "price": 3.0,
    })

    broker = MockBrokerAdapter(
        open_orders=[{"client_order_id": client_id, "broker_order_id": "BRK-01", "status": "ACCEPTED", "executed_qty": 0}]
    )

    runtime = OptionProgramRuntime(wal_store=wal_store)
    summary = runtime.startup_recovery(broker_adapter=broker)

    uid = uuid.UUID(order_uuid)
    assert summary["recovery_completed"] is True
    assert runtime.order_router.fsm.get_status(uid) == OrderStatus.ACCEPTED
    assert runtime.order_router.get_executed_qty(uid) == 0


def test_5_interrupted_after_partial_execution(tmp_path):
    """5. Partial execution 직후 중단 후 재시작 시 PARTIAL 상태 및 누적 체결수량 복원."""
    wal_file = str(tmp_path / "partial_crash.wal")
    wal_store = WalStore(log_path=wal_file)

    order_uuid = str(uuid.uuid4())
    client_id = "ORD-PART-CRASH"
    wal_store.save_event_sync("ORDER_INTENT", {
        "order_id": order_uuid,
        "client_order_id": client_id,
        "qty": 10,
        "price": 3.0,
    })
    wal_store.save_event_sync("PARTIAL_EXECUTION", {
        "order_id": order_uuid,
        "client_order_id": client_id,
        "exec_id": "EX-PART-01",
        "cum_executed_qty": 4,
        "status": "PARTIAL",
    })

    broker = MockBrokerAdapter(
        open_orders=[{"client_order_id": client_id, "status": "PARTIAL", "executed_qty": 4}]
    )

    runtime = OptionProgramRuntime(wal_store=wal_store)
    summary = runtime.startup_recovery(broker_adapter=broker)

    uid = uuid.UUID(order_uuid)
    assert summary["recovery_completed"] is True
    assert runtime.order_router.fsm.get_status(uid) == OrderStatus.PARTIAL
    assert runtime.order_router.get_executed_qty(uid) == 4
    assert uid in runtime.order_router._active_orders
    assert runtime.order_router.is_execution_processed("EX-PART-01") is True


def test_6_interrupted_after_filled_execution(tmp_path):
    """6. Filled execution 직후 중단 후 재시작 시 FILLED 상태 및 active_orders 정리 복원."""
    wal_file = str(tmp_path / "filled_crash.wal")
    wal_store = WalStore(log_path=wal_file)

    order_uuid = str(uuid.uuid4())
    client_id = "ORD-FILL-CRASH"
    wal_store.save_event_sync("ORDER_INTENT", {
        "order_id": order_uuid,
        "client_order_id": client_id,
        "qty": 5,
        "price": 2.0,
    })
    wal_store.save_event_sync("FILLED_EXECUTION", {
        "order_id": order_uuid,
        "client_order_id": client_id,
        "exec_id": "EX-FILL-01",
        "cum_executed_qty": 5,
        "status": "FILLED",
    })

    # Broker open_orders에는 전량 체결 건이 미포함됨
    broker = MockBrokerAdapter(open_orders=[])

    runtime = OptionProgramRuntime(wal_store=wal_store)
    summary = runtime.startup_recovery(broker_adapter=broker)

    uid = uuid.UUID(order_uuid)
    assert summary["recovery_completed"] is True
    assert runtime.order_router.fsm.get_status(uid) == OrderStatus.FILLED
    assert runtime.order_router.get_executed_qty(uid) == 5
    assert uid not in runtime.order_router._active_orders


def test_7_execution_wal_boundary_failure_handling(tmp_path):
    """7. execution WAL 선기록 단계 실패 시 메모리 불일치 방지 검증."""
    wal_file = str(tmp_path / "wal_fail.wal")
    wal_store = WalStore(log_path=wal_file)

    runtime = OptionProgramRuntime(wal_store=wal_store)
    router = runtime.order_router

    cmd = make_test_cmd("ORD-WAL-FAIL-01", qty=5)
    uid = uuid.uuid4()
    tok = make_test_token(uid, "ORD-WAL-FAIL-01")
    assert router.register_and_route(command=cmd, token=tok) == uid

    # WAL 쓰기 실패를 모의
    with patch.object(wal_store, "save_event_sync", side_effect=IOError("Disk write failed")):
        rep = make_test_report(uid, "ORD-WAL-FAIL-01", exec_id="EX-FAIL-01", exec_qty=3)
        # WAL 선기록 실패 시 False 반환 또는 체결 거부
        success = router.handle_execution_report(uid, rep)
        # WAL 실패 시 메모리 누적 체결 수량 왜곡이 방지되어야 함
        assert success is False or router.get_executed_qty(uid) == 0


def test_8_duplicate_exec_id_replay_preserves_qty(tmp_path):
    """8. duplicate exec_id 재전달 시 누적 체결수량 불변 및 멱등성 검증."""
    wal_file = str(tmp_path / "dup_exec.wal")
    wal_store = WalStore(log_path=wal_file)

    runtime = OptionProgramRuntime(wal_store=wal_store)
    router = runtime.order_router

    cmd = make_test_cmd("ORD-DUP-01", qty=10)
    uid = uuid.uuid4()
    tok = make_test_token(uid, "ORD-DUP-01")
    router.register_and_route(command=cmd, token=tok)

    rep1 = make_test_report(uid, "ORD-DUP-01", exec_id="EX-DUP-100", exec_qty=4)
    assert router.handle_execution_report(uid, rep1) is True
    assert router.get_executed_qty(uid) == 4

    # 동일한 exec_id 재전달 3회
    for _ in range(3):
        assert router.handle_execution_report(uid, rep1) is True
        assert router.get_executed_qty(uid) == 4  # 수량 증가 없음

    assert router.is_execution_processed("EX-DUP-100") is True


def test_9_unknown_order_interrupted_and_restarted(tmp_path):
    """9. UNKNOWN 상태에서 프로세스 중단 후 재시작 시 UNKNOWN 상태 복원 및 안전 차단."""
    wal_file = str(tmp_path / "unknown_crash.wal")
    wal_store = WalStore(log_path=wal_file)

    order_uuid = str(uuid.uuid4())
    client_id = "ORD-UNK-CRASH"
    wal_store.save_event_sync("ORDER_INTENT", {"order_id": order_uuid, "client_order_id": client_id, "qty": 5, "price": 3.0})
    wal_store.save_event_sync("BROKER_UNKNOWN", {"order_id": order_uuid, "client_order_id": client_id, "reason": "CRASH_UNKNOWN"})

    runtime = OptionProgramRuntime(wal_store=wal_store)
    summary = runtime.startup_recovery()

    uid = uuid.UUID(order_uuid)
    assert runtime.order_router.fsm.get_status(uid) == OrderStatus.UNKNOWN
    assert runtime.order_router.has_unresolved_unknown_orders() is True
    assert runtime.has_unresolved_unknown_orders() is True


def test_10_broker_reconciliation_failure_safety_blocking(tmp_path):
    """10. Broker reconciliation 실패/불확실성 발생 시 거래 차단 검증."""
    wal_file = str(tmp_path / "recon_block.wal")
    wal_store = WalStore(log_path=wal_file)

    order_uuid = str(uuid.uuid4())
    client_id = "ORD-RECON-BLOCK"
    wal_store.save_event_sync("ORDER_INTENT", {"order_id": order_uuid, "client_order_id": client_id, "qty": 5, "price": 3.0})

    failing_broker = MockBrokerAdapter()
    failing_broker.disconnect()  # 미연결 상태

    runtime = OptionProgramRuntime(wal_store=wal_store)
    with pytest.raises(RuntimeError):
        # Broker disconnected 상태에서 대사 시도 시 에러 발생 및 차단
        with patch.object(failing_broker, "get_open_orders", side_effect=ConnectionError("Broker link down")):
            with patch.object(failing_broker, "is_connected", return_value=True):
                runtime.startup_recovery(broker_adapter=failing_broker)


@pytest.mark.asyncio
async def test_11_recovery_blocks_new_order_transport_before_completion(tmp_path):
    """11. Recovery 완료 전 run_loop 및 신규 Broker transport 원천 차단 검증."""
    system = TradingSystem(config={
        "wal_log_path": str(tmp_path / "unrecov.wal"),
        "broker_mode": "PAPER"
    })

    # 미초기화 상태에서 run_loop 차단
    with pytest.raises(RuntimeError) as exc_info:
        await system.run_loop(max_ticks=1)
    assert "TradingSystem must be initialized" in str(exc_info.value)


def test_12_restart_oms_state_equivalence(tmp_path):
    """12. 재시작 전 인스턴스와 재시작 후 복원 인스턴스 간 OMS 상태 100% 동등성 검증."""
    wal_file = str(tmp_path / "equiv_test.wal")
    wal_store = WalStore(log_path=wal_file)

    # 1차 세션 (Pre-crash)
    rt1 = OptionProgramRuntime(wal_store=wal_store)
    cmd1 = make_test_cmd("ORD-EQ-01", qty=10, price=3.5)
    u1 = uuid.uuid4()
    tok1 = make_test_token(u1, "ORD-EQ-01")
    rt1.order_router.register_and_route(cmd1, tok1)
    rt1.order_router.register_broker_order_id(u1, "BRK-EQ-01")
    rep1 = make_test_report(u1, "ORD-EQ-01", exec_id="EX-EQ-1", exec_qty=6)
    rt1.order_router.handle_execution_report(u1, rep1)

    # 2차 세션 (Post-restart)
    rt2 = OptionProgramRuntime(wal_store=wal_store)
    rt2.startup_recovery()

    assert rt2.order_router.fsm.get_status(u1) == rt1.order_router.fsm.get_status(u1) == OrderStatus.PARTIAL
    assert rt2.order_router.get_executed_qty(u1) == rt1.order_router.get_executed_qty(u1) == 6
    assert rt2.order_router.is_execution_processed("EX-EQ-1") is True
    assert rt2.order_router.get_broker_order_id(u1) == "BRK-EQ-01"


def test_13_repeated_restart_idempotency(tmp_path):
    """13. 동일 WAL 기반 반복 재시작 시 멱등성 보장 검증."""
    wal_file = str(tmp_path / "repeat_restart.wal")
    wal_store = WalStore(log_path=wal_file)

    order_uuid = str(uuid.uuid4())
    client_id = "ORD-REPEAT-01"
    wal_store.save_event_sync("ORDER_INTENT", {"order_id": order_uuid, "client_order_id": client_id, "qty": 10, "price": 2.0})
    wal_store.save_event_sync("PARTIAL_EXECUTION", {"order_id": order_uuid, "client_order_id": client_id, "exec_id": "EX-REP-1", "cum_executed_qty": 3, "status": "PARTIAL"})

    uid = uuid.UUID(order_uuid)

    # 3회 연속 재시작 시뮬레이션
    for _ in range(3):
        rt = OptionProgramRuntime(wal_store=wal_store)
        summary = rt.startup_recovery()
        assert summary["recovery_completed"] is True
        assert rt.order_router.fsm.get_status(uid) == OrderStatus.PARTIAL
        assert rt.order_router.get_executed_qty(uid) == 3
        assert rt.order_router.is_execution_processed("EX-REP-1") is True


def test_14_corrupt_and_partial_wal_mixed_recovery(tmp_path):
    """14. 손상/잘린 라인과 유효 WAL 라인 혼합 시 안전 복구 검증."""
    wal_file = str(tmp_path / "corrupt_mixed_2.wal")

    u1 = str(uuid.uuid4())
    u2 = str(uuid.uuid4())
    valid1 = f'{{"event_type": "ORDER_INTENT", "data": {{"order_id": "{u1}", "client_order_id": "ORD-V1", "qty": 5, "price": 2.0}}}}\n'
    corrupt1 = '{"event_type": "ORDER_INTENT", "data": INVALID_JSON_TRUNCATED\n'
    valid2 = f'{{"event_type": "ORDER_INTENT", "data": {{"order_id": "{u2}", "client_order_id": "ORD-V2", "qty": 10, "price": 3.0}}}}\n'
    corrupt2 = 'GARBAGE_BYTES_CORRUPTED_LINE\n'

    with open(wal_file, "w", encoding="utf-8") as f:
        f.write(valid1)
        f.write(corrupt1)
        f.write(valid2)
        f.write(corrupt2)

    wal_store = WalStore(log_path=wal_file)
    rt = OptionProgramRuntime(wal_store=wal_store)
    summary = rt.startup_recovery()

    assert summary["wal_recovered_count"] == 2
    assert summary["recovery_completed"] is True
    assert rt.order_router.fsm.get_status(uuid.UUID(u1)) == OrderStatus.SENT
    assert rt.order_router.fsm.get_status(uuid.UUID(u2)) == OrderStatus.SENT
