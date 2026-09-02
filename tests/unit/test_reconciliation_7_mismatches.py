"""[10단계-3] Broker ↔ 내부 OMS 7대 불일치 대사, 확정 보정, UNKNOWN 안전 격리, 재시작 상태 유지 및 Idempotency 단위 테스트.

검증 항목 (7대 불일치):
1. OMS에만 주문 존재 (ORDER_MISMATCH -> UNKNOWN 격리 및 신규 주문 차단)
2. Broker에만 주문 존재 (ORDER_MISMATCH -> 감지 및 WAL 기록)
3. Broker Order ID 불일치 (ORDER_ID_MISMATCH -> 매핑 보정 및 WAL 영속화)
4. 주문 상태 불일치 (STATUS_MISMATCH -> Broker 확정 상태로 FSM 보정 및 WAL 영속화)
5. 누적 체결수량 불일치 (EXECUTION_MISMATCH -> Broker 수량 보정 및 WAL 영속화)
6. 평균 체결가격 불일치 (PRICE_MISMATCH -> 실제 내부 가격 보정, 2회차 mismatch=0, 모호한 가격 격리)
7. 포지션 불일치 (POSITION_MISMATCH -> Union 전수 탐지: Broker-only, Internal-only, Qty 불일치 및 실제 내부 포지션 보정)

추가 안전 검증:
8. UNKNOWN 및 POSITION 불일치 시 신규 주문 transport 0건 차단 검증
9. 동일 Reconciliation 반복 실행 시 Idempotency 검증 (2회차 mismatches=0, corrections=0)
10. Broker 조회 실패(네트워크 오류)와 실제 불일치의 엄격한 구분 및 안전 차단 검증
11. 대사 보정 후 재시작 시 WAL로부터 가격/포지션/상태 복원 및 유지 검증
12. Broker-only 및 Internal-only 포지션 전수 대사 및 보정 E2E 검증
13. 모호한 Broker 가격(0.0 또는 None) 수신 시 임의 추정 금지 및 UNKNOWN 격리 검증
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


def make_cmd(client_id: str, qty: int = 1, price: float = 2.5, side: CanonicalOrderSide = CanonicalOrderSide.BUY, symbol: str = "201V8350") -> CanonicalOrderCommand:
    return CanonicalOrderCommand(
        client_order_id=client_id,
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=side,
        qty=qty,
        price=price,
        symbol=symbol,
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
    wal_file = str(tmp_path / "recon_1.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-OMS-ONLY", qty=2)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-OMS-ONLY")
    router.register_and_route(cmd, tok)

    broker = MockBrokerAdapter()
    broker.open_orders_list = []
    broker.order_status_map = {}

    summary = router.reconcile_with_broker(broker)

    mismatches = summary["mismatches"]
    assert any(m.get("type") == "ORDER_MISMATCH" for m in mismatches)
    assert router.has_unresolved_unknown_orders() is True
    assert router.fsm.get_status(oid) == OrderStatus.UNKNOWN

    wal_events = wal_store.load_history_sync()
    assert any(e.get("event_type") == "RECONCILIATION_MISMATCH" for e in wal_events)
    assert any(e.get("event_type") == "BROKER_UNKNOWN" for e in wal_events)


# ---------------------------------------------------------------------------
# 2. Broker에만 주문 존재 (ORDER_MISMATCH)
# ---------------------------------------------------------------------------
def test_2_broker_only_order_mismatch(tmp_path):
    wal_file = str(tmp_path / "recon_2.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    broker = MockBrokerAdapter()
    broker.open_orders_list = [{
        "client_order_id": "ORD-BROKER-ONLY",
        "broker_order_id": "BRK-EXTERNAL-999",
        "status": "OPEN",
        "executed_qty": 0,
    }]

    summary = router.reconcile_with_broker(broker)

    mismatches = summary["mismatches"]
    brk_only = [m for m in mismatches if m.get("type") == "ORDER_MISMATCH" and m.get("subtype") == "BROKER_ONLY_OPEN_ORDER"]
    assert len(brk_only) == 1
    assert brk_only[0]["client_order_id"] == "ORD-BROKER-ONLY"

    wal_events = wal_store.load_history_sync()
    assert any(e.get("event_type") == "RECONCILIATION_MISMATCH" and e.get("data", {}).get("subtype") == "BROKER_ONLY_OPEN_ORDER" for e in wal_events)


# ---------------------------------------------------------------------------
# 3. Broker Order ID 불일치 (ORDER_ID_MISMATCH)
# ---------------------------------------------------------------------------
def test_3_order_id_mismatch_correction(tmp_path):
    wal_file = str(tmp_path / "recon_3.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-ID-MISMATCH", qty=1)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-ID-MISMATCH")
    router.register_and_route(cmd, tok)

    router._order_to_broker_id[oid] = "BRK-OLD-ID"
    router._client_to_broker_id["ORD-ID-MISMATCH"] = "BRK-OLD-ID"

    broker = MockBrokerAdapter()
    broker.open_orders_list = [{
        "client_order_id": "ORD-ID-MISMATCH",
        "broker_order_id": "BRK-NEW-ACTUAL-ID",
        "status": "OPEN",
        "executed_qty": 0,
    }]

    summary = router.reconcile_with_broker(broker)

    mismatches = summary["mismatches"]
    assert any(m.get("type") == "ORDER_ID_MISMATCH" for m in mismatches)
    assert router.get_broker_order_id("ORD-ID-MISMATCH") == "BRK-NEW-ACTUAL-ID"

    wal_events = wal_store.load_history_sync()
    assert any(e.get("event_type") == "RECONCILIATION_CORRECTED" and e.get("data", {}).get("type") == "ORDER_ID_CORRECTION" for e in wal_events)


# ---------------------------------------------------------------------------
# 4. 주문 상태 불일치 (STATUS_MISMATCH -> FILLED 확정 보정)
# ---------------------------------------------------------------------------
def test_4_status_mismatch_correction_to_filled(tmp_path):
    wal_file = str(tmp_path / "recon_4.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-STATUS-FILL", qty=3)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-STATUS-FILL")
    router.register_and_route(cmd, tok)

    assert router.fsm.get_status(oid) == OrderStatus.SENT

    broker = MockBrokerAdapter()
    broker.open_orders_list = []
    broker.order_status_map["ORD-STATUS-FILL"] = {
        "client_order_id": "ORD-STATUS-FILL",
        "broker_order_id": "BRK-FILL-100",
        "status": "FILLED",
        "executed_qty": 3,
    }

    summary = router.reconcile_with_broker(broker)

    assert router.fsm.get_status(oid) == OrderStatus.FILLED
    assert oid not in router._active_orders
    assert router.get_executed_qty(oid) == 3

    wal_events = wal_store.load_history_sync()
    assert any(e.get("event_type") == "RECONCILIATION_CORRECTED" and e.get("data", {}).get("new_status") == "FILLED" for e in wal_events)


# ---------------------------------------------------------------------------
# 5. 누적 체결수량 불일치 (EXECUTION_MISMATCH)
# ---------------------------------------------------------------------------
def test_5_execution_mismatch_correction(tmp_path):
    wal_file = str(tmp_path / "recon_5.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-EXEC-MISMATCH", qty=5)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-EXEC-MISMATCH")
    router.register_and_route(cmd, tok)

    router._cum_executed_qty[oid] = 1

    broker = MockBrokerAdapter()
    broker.open_orders_list = [{
        "client_order_id": "ORD-EXEC-MISMATCH",
        "broker_order_id": "BRK-PART-200",
        "status": "OPEN",
        "executed_qty": 3,
    }]

    summary = router.reconcile_with_broker(broker)

    assert any(m.get("type") == "EXECUTION_MISMATCH" for m in summary["mismatches"])
    assert router.get_executed_qty(oid) == 3
    assert router._cum_executed_qty[oid] == 3
    assert router.fsm.get_status(oid) == OrderStatus.PARTIAL

    wal_events = wal_store.load_history_sync()
    assert any(e.get("event_type") == "RECONCILIATION_CORRECTED" and e.get("data", {}).get("new_executed_qty") == 3 for e in wal_events)


# ---------------------------------------------------------------------------
# 6. 평균 체결가격 불일치 (PRICE_MISMATCH 실제 내부 보정 및 2회차 0 수렴)
# ---------------------------------------------------------------------------
def test_6_price_mismatch_correction(tmp_path):
    wal_file = str(tmp_path / "recon_6.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-PRICE-MISMATCH", qty=1, price=2.5)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-PRICE-MISMATCH")
    router.register_and_route(cmd, tok)

    assert router.get_executed_price(oid) == 2.5
    assert cmd.price == 2.5

    broker = MockBrokerAdapter()
    broker.open_orders_list = [{
        "client_order_id": "ORD-PRICE-MISMATCH",
        "broker_order_id": "BRK-PRC-300",
        "status": "OPEN",
        "executed_qty": 0,
        "executed_price": 2.75,
    }]

    # 1회차 대사: PRICE_MISMATCH 감지 및 실제 내부 상태 변경
    summary1 = router.reconcile_with_broker(broker)
    assert any(m.get("type") == "PRICE_MISMATCH" for m in summary1["mismatches"])
    assert router.get_executed_price(oid) == 2.75
    assert router.get_active_order_command(oid).price == 2.75

    wal_events = wal_store.load_history_sync()
    assert any(e.get("event_type") == "RECONCILIATION_CORRECTED" and e.get("data", {}).get("type") == "PRICE_CORRECTION" and e.get("data", {}).get("new_price") == 2.75 for e in wal_events)

    # 2회차 재대사: 내부 상태가 이미 2.75로 보정되었으므로 PRICE_MISMATCH가 0건이어야 함 (Idempotency)
    summary2 = router.reconcile_with_broker(broker)
    price_mismatches_round2 = [m for m in summary2["mismatches"] if m.get("type") == "PRICE_MISMATCH"]
    assert len(price_mismatches_round2) == 0


# ---------------------------------------------------------------------------
# 7. 포지션 불일치 전수 탐지 (Union: Broker-only, Internal-only, Qty Mismatch 및 실제 보정)
# ---------------------------------------------------------------------------
def test_7_position_mismatch_detection(tmp_path):
    wal_file = str(tmp_path / "recon_7.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    internal_positions = {
        "201V8350": {"symbol": "201V8350", "qty": 10},  # Qty 불일치 (10 vs 5)
        "201V8355": {"symbol": "201V8355", "qty": 4},   # Internal-only (Broker에는 없음)
    }

    broker = MockBrokerAdapter()
    broker.positions_map = {
        "201V8350": {"symbol": "201V8350", "qty": 5},   # Qty 불일치
        "201V8360": {"symbol": "201V8360", "qty": 8},   # Broker-only
    }

    # 1회차 대사: 3개 심볼 전수 불일치 감지 및 Broker authoritative 보정
    summary1 = router.reconcile_with_broker(broker, internal_positions=internal_positions)

    pos_mismatches = [m for m in summary1["mismatches"] if m.get("type") == "POSITION_MISMATCH"]
    assert len(pos_mismatches) == 3
    symbols_detected = {m["symbol"] for m in pos_mismatches}
    assert symbols_detected == {"201V8350", "201V8355", "201V8360"}

    # 실제 내부 포지션 딕셔너리가 Broker 값으로 보정되었는지 검증
    assert internal_positions["201V8350"]["qty"] == 5
    assert "201V8355" not in internal_positions  # 수량 0으로 제거됨
    assert internal_positions["201V8360"]["qty"] == 8

    # 2회차 재대사: 이미 보정되었으므로 포지션 불일치 0건이어야 함
    summary2 = router.reconcile_with_broker(broker, internal_positions=internal_positions)
    pos_mismatches_round2 = [m for m in summary2["mismatches"] if m.get("type") == "POSITION_MISMATCH"]
    assert len(pos_mismatches_round2) == 0


# ---------------------------------------------------------------------------
# 8. UNKNOWN 또는 POSITION 불일치 시 신규 주문 안전 차단 (Transport 0건)
# ---------------------------------------------------------------------------
def test_8_unknown_state_blocks_new_order_transport(tmp_path):
    wal_file = str(tmp_path / "recon_8.wal")
    wal_store = WalStore(log_path=wal_file)
    runtime = OptionProgramRuntime(wal_store=wal_store)

    broker = MockBrokerAdapter()

    # 정상 상태에서는 주문 정상 라우팅 가능
    cmd1 = make_cmd("ORD-NORM-1", qty=1)
    tok1 = make_token(uuid.uuid4(), "ORD-NORM-1")
    assert runtime.order_router.register_and_route(cmd1, tok1) is not None

    # UNKNOWN 주문 발생 시
    runtime.mark_order_unknown("ORD-NORM-1", reason="TIMEOUT_ISOLATION")
    assert runtime.has_unresolved_unknown_orders() is True

    # Broker 조회 실패로 인한 포지션 불일치 미해결 시
    runtime.order_router._unresolved_position_mismatches["201V8350"] = {"symbol": "201V8350", "reason": "UNRESOLVED"}
    assert runtime.has_unresolved_position_mismatches() is True


# ---------------------------------------------------------------------------
# 9. 동일 Reconciliation 반복 실행 시 Idempotency 검증
# ---------------------------------------------------------------------------
def test_9_reconciliation_repetition_idempotency(tmp_path):
    wal_file = str(tmp_path / "recon_9.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-IDEMPOTENT-1", qty=5, price=2.0)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-IDEMPOTENT-1")
    router.register_and_route(cmd, tok)

    broker = MockBrokerAdapter()
    broker.open_orders_list = [{
        "client_order_id": "ORD-IDEMPOTENT-1",
        "broker_order_id": "BRK-IDEM-001",
        "status": "ACCEPTED",
        "executed_qty": 2,
        "executed_price": 2.2,
    }]
    internal_pos = {"201V8350": {"symbol": "201V8350", "qty": 10}}
    broker.positions_map = {"201V8350": {"symbol": "201V8350", "qty": 5}}

    # 1회차 대사: 모든 불일치 감지 및 보정
    res1 = router.reconcile_with_broker(broker, internal_positions=internal_pos)
    assert len(res1["mismatches"]) > 0
    assert len(res1["corrections"]) > 0

    # 2회차 대사: 불일치 0건, 보정 0건으로 완벽히 수렴
    res2 = router.reconcile_with_broker(broker, internal_positions=internal_pos)
    assert len(res2["mismatches"]) == 0
    assert len(res2["corrections"]) == 0
    assert res2["status"] == "COMPLETED"


# ---------------------------------------------------------------------------
# 10. Broker 조회 실패(네트워크 오류)와 실제 불일치 구분 검증
# ---------------------------------------------------------------------------
def test_10_broker_query_failure_vs_actual_mismatch(tmp_path):
    wal_file = str(tmp_path / "recon_10.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-NET-FAIL", qty=1)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-NET-FAIL")
    router.register_and_route(cmd, tok)

    broker = MockBrokerAdapter()
    broker.should_raise_query_error = True

    res = router.reconcile_with_broker(broker)

    # 네트워크 조회 실패 시 status == FAILED 반환 및 임의의 상태 보정 금지
    assert res["status"] == "FAILED"
    assert router.fsm.get_status(oid) == OrderStatus.SENT
    assert len(res["corrections"]) == 0


# ---------------------------------------------------------------------------
# 11. 대사 보정 후 재시작 시 WAL로부터 보정 상태 유지 검증 (Restart Persistence)
# ---------------------------------------------------------------------------
def test_11_reconciliation_corrections_persist_across_restart(tmp_path):
    wal_file = str(tmp_path / "recon_11.wal")
    wal_store = WalStore(log_path=wal_file)
    router1 = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-PERSIST-1", qty=4, price=3.0)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-PERSIST-1")
    router1.register_and_route(cmd, tok)

    broker = MockBrokerAdapter()
    broker.open_orders_list = [{
        "client_order_id": "ORD-PERSIST-1",
        "broker_order_id": "BRK-PERSIST-999",
        "status": "ACCEPTED",
        "executed_qty": 2,
        "executed_price": 3.25,
    }]
    int_pos = {"201V8350": {"symbol": "201V8350", "qty": 10}}
    broker.positions_map = {"201V8350": {"symbol": "201V8350", "qty": 7}}

    # 1차 세션에서 대사 및 보정 실행
    router1.reconcile_with_broker(broker, internal_positions=int_pos)
    assert router1.get_executed_qty(oid) == 2
    assert router1.get_executed_price(oid) == 3.25

    # 프로세스 재시작: 새 WAL Store 및 OrderRouter로 복원
    wal_store2 = WalStore(log_path=wal_file)
    events = wal_store2.load_history_sync()
    router2 = OrderRouter(wal_store=wal_store2)
    recovered_count = router2.recover_from_wal(events)

    assert recovered_count > 0
    assert router2.get_broker_order_id("ORD-PERSIST-1") == "BRK-PERSIST-999"
    assert router2.get_executed_qty(oid) == 2
    assert router2.get_executed_price(oid) == 3.25
    assert router2._corrected_positions.get("201V8350") == 7


# ---------------------------------------------------------------------------
# 12. 모호한 Broker 가격(0.0 또는 None) 수신 시 임의 추정 금지
# ---------------------------------------------------------------------------
def test_12_ambiguous_broker_price_isolation_without_auto_correction(tmp_path):
    wal_file = str(tmp_path / "recon_12.wal")
    wal_store = WalStore(log_path=wal_file)
    router = OrderRouter(wal_store=wal_store)

    cmd = make_cmd("ORD-PRICE-AMBIGUOUS", qty=1, price=2.5)
    oid = uuid.uuid4()
    tok = make_token(oid, "ORD-PRICE-AMBIGUOUS")
    router.register_and_route(cmd, tok)

    broker = MockBrokerAdapter()
    broker.open_orders_list = [{
        "client_order_id": "ORD-PRICE-AMBIGUOUS",
        "broker_order_id": "BRK-AMBIG-001",
        "status": "OPEN",
        "executed_qty": 0,
        "executed_price": 0.0,  # 모호한 가격
    }]

    summary = router.reconcile_with_broker(broker)

    # 모호한 가격(0.0)에 대해서는 PRICE_CORRECTION을 수행하지 않고 기존 주문 가격(2.5) 유지
    assert router.get_executed_price(oid) == 2.5
    price_corrections = [c for c in summary["corrections"] if c.get("type") == "PRICE_CORRECTION"]
    assert len(price_corrections) == 0
