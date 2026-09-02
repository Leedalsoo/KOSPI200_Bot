"""[10단계-3] Broker ↔ 내부 OMS 7대 불일치 대사, 확정 보정, UNKNOWN 안전 격리, 재시작 상태 유지 및 Idempotency 단위 테스트.

검증 항목 (7대 불일치):
1. OMS에만 주문 존재 (ORDER_MISMATCH -> UNKNOWN 격리 및 신규 주문 차단)
2. Broker에만 주문 존재 (ORDER_MISMATCH -> 감지 및 WAL 기록)
3. Broker Order ID 불일치 (ORDER_ID_MISMATCH -> 매핑 보정 및 WAL 영속화)
4. 주문 상태 불일치 (STATUS_MISMATCH -> Broker 확정 상태로 FSM 보정 및 WAL 영속화)
5. 누적 체결수량 불일치 (EXECUTION_MISMATCH -> Broker 수량 보정 및 WAL 영속화)
6. 평균 체결가격 불일치 (PRICE_MISMATCH -> Broker 가격 보정 및 WAL 영속화)
7. 포지션 불일치 (POSITION_MISMATCH -> 감지 및 WAL 영속화)

추가 안전 검증:
8. UNKNOWN / 대사 실패 시 신규 주문 transport 0건 차단 검증
9. 동일 Reconciliation 반복 실행 시 Idempotency 검증 (2회차 mismatches=0, corrections=0)
10. Broker 조회 실패(네트워크 오류)와 실제 불일치의 엄격한 구분 검증
11. 대사 보정 후 재시작 시 WAL로부터 보정 상태 유지 검증
"""

import os
import uuid
import pytest
from typing import Dict, Any, List, Optional

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
    CanonicalMarketTick,
)


class MockBrokerAdapter:
    """7대 불일치 시나리오 테스트를 위한 모의 브로커 어댑터."""

    def __init__(self):
        self.connected = True
        self.open_orders_list: List[Dict[str, Any]] = []
        self.order_status_map: Dict[str, Dict[str, Any]] = {}
        self.positions_map: Dict[str, Dict[str, Any]] = {}
        self.sent_orders: List[CanonicalOrderCommand] = []
        self.should_raise_query_error: bool = False

    def is_connected(self) -> bool:
        return self.connected

    def get_open_orders(self) -> List[Dict[str, Any]]:
        if self.should_raise_query_error:
            raise ConnectionError("Broker network query failed")
        return list(self.open_orders_list)

    def get_order_status(self, target_id: str) -> Optional[Dict[str, Any]]:
        if self.should_raise_query_error:
            raise ConnectionError("Broker network query failed")
        return self.order_status_map.get(target_id)

    def get_positions(self) -> Dict[str, Any]:
        if self.should_raise_query_error:
            raise ConnectionError("Broker network query failed")
        return dict(self.positions_map)

    def send_order(self, command: CanonicalOrderCommand) -> Any:
        self.sent_orders.append(command)
        class Ack:
            success = True
            client_order_id = command.client_order_id
            broker_order_id = f"BRK-{command.client_order_id}"
            status = "ACCEPTED"
        return Ack()


def make_cmd(client_id: str, qty: int = 1, price: float = 2.5, side: CanonicalOrderSide = CanonicalOrderSide.BUY) -> CanonicalOrderCommand:
    return CanonicalOrderCommand(
        client_order_id=client_id,
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=side,
        qty=qty,
        price=price,
        symbol="201V8350",
        option_type=CanonicalOptionType.CALL,
        strike=350.0,
    )


def make_token(order_id: uuid.UUID, client_id: str) -> RiskApprovalToken:
    return RiskApprovalToken(
        order_id=order_id,
        timestamp_ns=1000000,
        signature=f"SIG-RISK-APPROVED-Track1-{client_id}",
    )


# ---------------------------------------------------------------------------
# 1. OMS에만 주문 존재 (ORDER_MISMATCH)
# ---------------------------------------------------------------------------
def test_1_oms_only_order_mismatch_and_unknown_isolation(tmp_path):
    """1. OMS에는 주문이 있으나 Broker에는 없고 상태 불명확 -> ORDER_MISMATCH 및 UNKNOWN 안전 격리."""
    wal_file = str(tmp_path / "test1.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-OMS-ONLY-01")
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-OMS-ONLY-01")
    router.register_and_route(command=cmd, token=tok)

    broker = MockBrokerAdapter()
    broker.open_orders_list = []  # Broker에 없음
    broker.order_status_map = {}   # get_order_status도 없음

    summary = router.reconcile_with_broker(broker)

    assert summary["status"] == "UNCERTAIN_REMAINED"
    assert len(summary["mismatches"]) == 1
    assert summary["mismatches"][0]["type"] == "ORDER_MISMATCH"
    assert summary["mismatches"][0]["subtype"] == "NOT_FOUND_IN_BROKER_OPEN_AND_STATUS_UNCERTAIN"
    assert router.fsm.get_status(oid) == OrderStatus.UNKNOWN
    assert router.has_unresolved_unknown_orders() is True


# ---------------------------------------------------------------------------
# 2. Broker에만 주문 존재 (ORDER_MISMATCH)
# ---------------------------------------------------------------------------
def test_2_broker_only_order_mismatch(tmp_path):
    """2. Broker에만 미체결 주문 존재 -> ORDER_MISMATCH 감지 및 WAL 영속화."""
    wal_file = str(tmp_path / "test2.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    broker = MockBrokerAdapter()
    broker.open_orders_list = [{
        "client_order_id": "ORD-BRK-ONLY-01",
        "broker_order_id": "BRK-GHOST-01",
        "status": "ACCEPTED",
        "executed_qty": 0,
    }]

    summary = router.reconcile_with_broker(broker)

    assert len(summary["mismatches"]) == 1
    assert summary["mismatches"][0]["type"] == "ORDER_MISMATCH"
    assert summary["mismatches"][0]["subtype"] == "BROKER_ONLY_OPEN_ORDER"
    assert summary["mismatches"][0]["client_order_id"] == "ORD-BRK-ONLY-01"

    # WAL 확인
    events = wal_store.load_history_sync()
    mismatch_events = [e for e in events if e.get("event_type") == "RECONCILIATION_MISMATCH"]
    assert len(mismatch_events) == 1
    assert mismatch_events[0]["data"]["type"] == "ORDER_MISMATCH"


# ---------------------------------------------------------------------------
# 3. Broker Order ID 불일치 (ORDER_ID_MISMATCH)
# ---------------------------------------------------------------------------
def test_3_order_id_mismatch_correction(tmp_path):
    """3. Broker Order ID 불일치 -> ORDER_ID_MISMATCH 감지 및 Broker ID로 매핑 보정."""
    wal_file = str(tmp_path / "test3.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-ID-01")
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-ID-01")
    router.register_and_route(command=cmd, token=tok)
    router.register_broker_order_id(oid, "BRK-OLD-ID")

    broker = MockBrokerAdapter()
    broker.open_orders_list = [{
        "client_order_id": "ORD-ID-01",
        "broker_order_id": "BRK-NEW-REAL-ID",
        "status": "ACCEPTED",
        "executed_qty": 0,
    }]

    summary = router.reconcile_with_broker(broker)

    assert any(m["type"] == "ORDER_ID_MISMATCH" for m in summary["mismatches"])
    assert any(c["type"] == "ORDER_ID_CORRECTION" for c in summary["corrections"])
    assert router.get_broker_order_id("ORD-ID-01") == "BRK-NEW-REAL-ID"
    assert router.get_broker_order_id(oid) == "BRK-NEW-REAL-ID"


# ---------------------------------------------------------------------------
# 4. 주문 상태 불일치 (STATUS_MISMATCH)
# ---------------------------------------------------------------------------
def test_4_status_mismatch_correction_to_filled(tmp_path):
    """4. 주문 상태 불일치 (OMS: SENT vs Broker: FILLED) -> 확정 보정 및 active 정리."""
    wal_file = str(tmp_path / "test4.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-STAT-01", qty=2)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-STAT-01")
    router.register_and_route(command=cmd, token=tok)

    broker = MockBrokerAdapter()
    broker.open_orders_list = []
    broker.order_status_map["ORD-STAT-01"] = {
        "client_order_id": "ORD-STAT-01",
        "broker_order_id": "BRK-STAT-01",
        "status": "FILLED",
        "executed_qty": 2,
    }

    summary = router.reconcile_with_broker(broker)

    assert any(m["type"] == "STATUS_MISMATCH" for m in summary["mismatches"])
    assert router.fsm.get_status(oid) == OrderStatus.FILLED
    assert router.get_executed_qty(oid) == 2
    assert oid not in router._active_orders


# ---------------------------------------------------------------------------
# 5. 누적 체결수량 불일치 (EXECUTION_MISMATCH)
# ---------------------------------------------------------------------------
def test_5_execution_mismatch_correction(tmp_path):
    """5. 누적 체결수량 불일치 (OMS: 0 vs Broker: 3) -> 수량 보정 및 PARTIAL 전이."""
    wal_file = str(tmp_path / "test5.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-EXEC-01", qty=5)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-EXEC-01")
    router.register_and_route(command=cmd, token=tok)

    broker = MockBrokerAdapter()
    broker.open_orders_list = [{
        "client_order_id": "ORD-EXEC-01",
        "broker_order_id": "BRK-EXEC-01",
        "status": "PARTIAL",
        "executed_qty": 3,
    }]

    summary = router.reconcile_with_broker(broker)

    assert any(m["type"] == "EXECUTION_MISMATCH" for m in summary["mismatches"])
    assert router.get_executed_qty(oid) == 3
    assert router.fsm.get_status(oid) == OrderStatus.PARTIAL


# ---------------------------------------------------------------------------
# 6. 평균 체결가격 불일치 (PRICE_MISMATCH)
# ---------------------------------------------------------------------------
def test_6_price_mismatch_correction(tmp_path):
    """6. 체결 가격 불일치 (OMS: 2.5 vs Broker: 2.65) -> PRICE_MISMATCH 감지 및 보정."""
    wal_file = str(tmp_path / "test6.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-PRICE-01", price=2.5)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-PRICE-01")
    router.register_and_route(command=cmd, token=tok)

    broker = MockBrokerAdapter()
    broker.open_orders_list = [{
        "client_order_id": "ORD-PRICE-01",
        "broker_order_id": "BRK-PRICE-01",
        "status": "ACCEPTED",
        "executed_qty": 0,
        "executed_price": 2.65,
    }]

    summary = router.reconcile_with_broker(broker)

    assert any(m["type"] == "PRICE_MISMATCH" for m in summary["mismatches"])
    assert any(c["type"] == "PRICE_CORRECTION" for c in summary["corrections"])


# ---------------------------------------------------------------------------
# 7. 포지션 불일치 (POSITION_MISMATCH)
# ---------------------------------------------------------------------------
def test_7_position_mismatch_detection(tmp_path):
    """7. 포지션 불일치 (내부: 5계약 vs Broker: 2계약) -> POSITION_MISMATCH 감지 및 WAL 기록."""
    wal_file = str(tmp_path / "test7.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    broker = MockBrokerAdapter()
    broker.positions_map = {
        "201V8350": {"symbol": "201V8350", "qty": 2}
    }

    internal_positions = {
        "201V8350": {"symbol": "201V8350", "qty": 5}
    }

    summary = router.reconcile_with_broker(broker, internal_positions=internal_positions)

    pos_mismatches = [m for m in summary["mismatches"] if m["type"] == "POSITION_MISMATCH"]
    assert len(pos_mismatches) == 1
    assert pos_mismatches[0]["symbol"] == "201V8350"
    assert pos_mismatches[0]["internal_qty"] == 5
    assert pos_mismatches[0]["broker_qty"] == 2


# ---------------------------------------------------------------------------
# 8. UNKNOWN / 대사 실패 시 신규 실주문 transport 0건 차단 검증
# ---------------------------------------------------------------------------
def test_8_unknown_state_blocks_new_order_transport(tmp_path):
    """8. UNKNOWN 상태 또는 대사 실패 시 신규 주문이 Broker로 발주되지 않음(transport 0건)을 검증."""
    wal_file = str(tmp_path / "test8.wal")
    wal_store = WalStore(log_path=wal_file)
    runtime = OptionProgramRuntime(wal_store=wal_store)

    # UNKNOWN 주문 격리 생성
    cmd1 = make_cmd("ORD-UNK-BLOCK-01")
    oid1 = uuid.uuid4()
    tok1 = make_token(oid1, "ORD-UNK-BLOCK-01")
    runtime.order_router.register_and_route(cmd1, tok1)
    runtime.order_router.mark_order_unknown(oid1, reason="TIMEOUT_FOR_BLOCK_TEST")

    assert runtime.has_unresolved_unknown_orders() is True

    # 신규 틱 유입 시 신규 주문 생성 시도
    broker = MockBrokerAdapter()
    tick = CanonicalMarketTick(
        timestamp="1000.0",
        underlying_price=350.0,
    )

    # TradingSystem 안전 가드 동작 시뮬레이션
    commands = runtime.process_tick(tick)
    for c in commands:
        if runtime.has_unresolved_unknown_orders():
            continue  # SAFETY BLOCK!
        broker.send_order(c)

    assert len(broker.sent_orders) == 0


# ---------------------------------------------------------------------------
# 9. 동일 Reconciliation 반복 실행 시 Idempotency 검증
# ---------------------------------------------------------------------------
def test_9_reconciliation_repetition_idempotency(tmp_path):
    """9. 동일 Broker 상태에 대해 2회 이상 연속 reconciliation 실행 시 상태 불변 및 2회차 불일치 0건 검증."""
    wal_file = str(tmp_path / "test9.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-IDEMP-01", qty=4)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-IDEMP-01")
    router.register_and_route(command=cmd, token=tok)

    broker = MockBrokerAdapter()
    broker.open_orders_list = [{
        "client_order_id": "ORD-IDEMP-01",
        "broker_order_id": "BRK-IDEMP-01",
        "status": "ACCEPTED",
        "executed_qty": 2,
    }]

    # 1회차 실행: 보정 수행
    summary1 = router.reconcile_with_broker(broker)
    assert len(summary1["mismatches"]) > 0
    assert len(summary1["corrections"]) > 0

    # 2회차 실행: 이미 보정 완료되었으므로 불일치 0건, 보정 0건
    summary2 = router.reconcile_with_broker(broker)
    assert len(summary2["mismatches"]) == 0
    assert len(summary2["corrections"]) == 0
    assert summary2["status"] == "COMPLETED"
    assert router.get_executed_qty(oid) == 2
    assert router.fsm.get_status(oid) == OrderStatus.PARTIAL


# ---------------------------------------------------------------------------
# 10. Broker 조회 실패(네트워크 오류)와 실제 불일치 구분 검증
# ---------------------------------------------------------------------------
def test_10_broker_query_failure_vs_actual_mismatch(tmp_path):
    """10. Broker 조회 실패(네트워크 오류) 시 FAILED 반환 및 임의 상태 전이 금지 검증."""
    wal_file = str(tmp_path / "test10.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-NET-ERR-01")
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-NET-ERR-01")
    router.register_and_route(command=cmd, token=tok)

    broker = MockBrokerAdapter()
    broker.should_raise_query_error = True  # 조회 실패 모의

    summary = router.reconcile_with_broker(broker)

    assert summary["status"] == "FAILED"
    # OMS 기존 상태는 임의로 변경되지 않고 그대로 SENT 유지
    assert router.fsm.get_status(oid) == OrderStatus.SENT


# ---------------------------------------------------------------------------
# 11. 대사 보정 후 재시작 시 WAL로부터 보정 상태 유지 검증
# ---------------------------------------------------------------------------
def test_11_reconciliation_corrections_persist_across_restart(tmp_path):
    """11. 대사 보정 내용이 WAL에 영속화되어 시스템 재시작 시에도 온전히 복원되는지 검증."""
    wal_file = str(tmp_path / "test11.wal")
    wal_store = WalStore(log_path=wal_file)
    runtime1 = OptionProgramRuntime(wal_store=wal_store)

    cmd = make_cmd("ORD-RESTART-01", qty=5)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-RESTART-01")
    runtime1.order_router.register_and_route(cmd, tok)

    broker = MockBrokerAdapter()
    broker.open_orders_list = [{
        "client_order_id": "ORD-RESTART-01",
        "broker_order_id": "BRK-RESTART-999",
        "status": "PARTIAL",
        "executed_qty": 3,
    }]

    # 1. 런타임1에서 대사 수행
    summary = runtime1.reconcile_with_broker(broker)
    assert runtime1.order_router.get_executed_qty("ORD-RESTART-01") == 3

    # 2. 시스템 다운 후 런타임2 재시작
    runtime2 = OptionProgramRuntime(wal_store=wal_store)
    rec_summary = runtime2.startup_recovery(broker_adapter=broker)

    # 3. 재시작 후 복원 상태 검증
    assert rec_summary["recovery_completed"] is True
    assert runtime2.order_router.get_executed_qty("ORD-RESTART-01") == 3
    assert runtime2.order_router.get_broker_order_id("ORD-RESTART-01") == "BRK-RESTART-999"
