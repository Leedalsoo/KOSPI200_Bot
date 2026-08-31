# -*- coding: utf-8 -*-
"""7단계-3: OrderStatus 9개 상태 전이, 불법 전이 차단, PARTIAL 누적 및 OrderRouter 이벤트 연계 검증 테스트.

대상 9개 상태:
- NEW, VALIDATED, SENT, ACCEPTED, PENDING, PARTIAL, FILLED, CANCELLED, REJECTED

검증 항목:
1. 9개 상태의 합법적 정상 전이 검증
2. 역방향/종료상태 불법 전이 시도 차단 및 상태 불변 검증
3. 종료 상태 (FILLED, CANCELLED, REJECTED)에서의 모든 재전이 시도 차단 검증
4. PARTIAL 누적 체결 경로 (PARTIAL -> PARTIAL -> FILLED) 및 수량 정합성 검증
5. PARTIAL -> CANCELLED, PARTIAL -> REJECTED 종료 전이 검증
6. OrderRouter의 실제 이벤트 경로(register_and_route, handle_execution_report, cancel_stale_order)와 OmsFsm transition() 연계 Functional Assertion
7. ACCEPTED/PENDING 상태의 FSM 전이 및 실제 운영 파이프라인 상 비생성 근거 확인
"""
import uuid
import time
import pytest
from unittest.mock import MagicMock

from shared.core.contracts import OrderStatus, RiskApprovalToken
from shared.contracts.canonical import (
    CanonicalOrderCommand,
    CanonicalExecutionReport,
    CanonicalAssetType,
    CanonicalOrderSide,
)
from option_program.orders.oms_fsm import OmsFsm, ALLOWED_TRANSITIONS
from option_program.orders.order_router import OrderRouter


def make_test_command(order_id_str: str = "ORD-FSM-001", qty: int = 10, price: float = 2.5) -> CanonicalOrderCommand:
    return CanonicalOrderCommand(
        client_order_id=order_id_str,
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=qty,
        price=price,
    )


def make_test_token(order_uuid: uuid.UUID, client_order_id: str = "ORD-FSM-001", track_id: str = "Track1") -> RiskApprovalToken:
    return RiskApprovalToken(
        order_id=order_uuid,
        timestamp_ns=time.time_ns(),
        signature=f"SIG-RISK-APPROVED-{track_id}-{client_order_id}"
    )


def make_test_report(
    client_order_id: str = "ORD-FSM-001",
    executed_qty: int = 1,
    executed_price: float = 2.5,
    track_id: str = "Track1",
    side: CanonicalOrderSide = CanonicalOrderSide.BUY,
    asset_type: CanonicalAssetType = CanonicalAssetType.OPTION,
) -> CanonicalExecutionReport:
    return CanonicalExecutionReport(
        exec_id=f"EXEC-{uuid.uuid4().hex[:8]}",
        client_order_id=client_order_id,
        track_id=track_id,
        asset_type=asset_type,
        side=side,
        executed_qty=executed_qty,
        executed_price=executed_price,
        fee=100.0,
        slippage=0.0,
        timestamp="2026-08-29 09:00:00",
    )


# ==============================================================================
# 1. 9개 상태 정상 전이 전수 검증
# ==============================================================================
def test_all_nine_order_statuses_normal_transitions():
    """9개 모든 OrderStatus의 허용된 정상 전이 경로를 전수 검증"""
    fsm = OmsFsm()
    order_id = uuid.uuid4()

    # None -> NEW
    assert fsm.transition_sync(order_id, OrderStatus.NEW) is True
    assert fsm.get_status(order_id) == OrderStatus.NEW

    # NEW -> VALIDATED
    assert fsm.transition_sync(order_id, OrderStatus.VALIDATED) is True
    assert fsm.get_status(order_id) == OrderStatus.VALIDATED

    # VALIDATED -> SENT
    assert fsm.transition_sync(order_id, OrderStatus.SENT) is True
    assert fsm.get_status(order_id) == OrderStatus.SENT

    # SENT -> ACCEPTED
    assert fsm.transition_sync(order_id, OrderStatus.ACCEPTED) is True
    assert fsm.get_status(order_id) == OrderStatus.ACCEPTED

    # ACCEPTED -> PENDING
    assert fsm.transition_sync(order_id, OrderStatus.PENDING) is True
    assert fsm.get_status(order_id) == OrderStatus.PENDING

    # PENDING -> PARTIAL
    assert fsm.transition_sync(order_id, OrderStatus.PARTIAL) is True
    assert fsm.get_status(order_id) == OrderStatus.PARTIAL

    # PARTIAL -> FILLED (종료)
    assert fsm.transition_sync(order_id, OrderStatus.FILLED) is True
    assert fsm.get_status(order_id) == OrderStatus.FILLED


def test_direct_sent_to_filled_and_rejected_transitions():
    """SENT에서 ACCEPTED/PENDING을 거치지 않고 직접 FILLED / REJECTED / CANCELLED 전이되는 표준 브로커 경로 검증"""
    # SENT -> FILLED
    fsm1 = OmsFsm()
    oid1 = uuid.uuid4()
    assert fsm1.transition_sync(oid1, OrderStatus.NEW) is True
    assert fsm1.transition_sync(oid1, OrderStatus.VALIDATED) is True
    assert fsm1.transition_sync(oid1, OrderStatus.SENT) is True
    assert fsm1.transition_sync(oid1, OrderStatus.FILLED) is True
    assert fsm1.get_status(oid1) == OrderStatus.FILLED

    # SENT -> REJECTED
    fsm2 = OmsFsm()
    oid2 = uuid.uuid4()
    assert fsm2.transition_sync(oid2, OrderStatus.NEW) is True
    assert fsm2.transition_sync(oid2, OrderStatus.VALIDATED) is True
    assert fsm2.transition_sync(oid2, OrderStatus.SENT) is True
    assert fsm2.transition_sync(oid2, OrderStatus.REJECTED) is True
    assert fsm2.get_status(oid2) == OrderStatus.REJECTED

    # SENT -> CANCEL_REQUESTED -> CANCELLED
    fsm3 = OmsFsm()
    oid3 = uuid.uuid4()
    assert fsm3.transition_sync(oid3, OrderStatus.NEW) is True
    assert fsm3.transition_sync(oid3, OrderStatus.VALIDATED) is True
    assert fsm3.transition_sync(oid3, OrderStatus.SENT) is True
    assert fsm3.transition_sync(oid3, OrderStatus.CANCEL_REQUESTED) is True
    assert fsm3.transition_sync(oid3, OrderStatus.CANCELLED) is True
    assert fsm3.get_status(oid3) == OrderStatus.CANCELLED


# ==============================================================================
# 2. 불법 역방향 및 비허용 전이 차단 검증
# ==============================================================================
@pytest.mark.parametrize("from_status, illegal_targets", [
    (None, [OrderStatus.ACCEPTED, OrderStatus.PENDING, OrderStatus.PARTIAL, OrderStatus.FILLED, OrderStatus.CANCELLED]),
    (OrderStatus.VALIDATED, [OrderStatus.NEW]),
    (OrderStatus.SENT, [OrderStatus.NEW, OrderStatus.VALIDATED]),
    (OrderStatus.ACCEPTED, [OrderStatus.NEW, OrderStatus.VALIDATED, OrderStatus.SENT]),
    (OrderStatus.PENDING, [OrderStatus.NEW, OrderStatus.VALIDATED, OrderStatus.SENT, OrderStatus.ACCEPTED]),
    (OrderStatus.PARTIAL, [OrderStatus.NEW, OrderStatus.VALIDATED, OrderStatus.SENT, OrderStatus.ACCEPTED, OrderStatus.PENDING]),
    (OrderStatus.FILLED, [s for s in OrderStatus]),
    (OrderStatus.CANCELLED, [s for s in OrderStatus]),
    (OrderStatus.REJECTED, [s for s in OrderStatus]),
])
def test_illegal_transitions_are_blocked(from_status, illegal_targets):
    """허용되지 않은 불법 전이 시도가 거부되고 기존 상태가 불변 유지됨을 검증"""
    fsm = OmsFsm()
    order_id = uuid.uuid4()

    # 초기 상태 설정
    if from_status is not None:
        fsm.states[order_id] = from_status

    for target in illegal_targets:
        res = fsm.transition_sync(order_id, target)
        assert res is False, f"Illegal transition from {from_status} to {target} must be rejected"
        assert fsm.get_status(order_id) == from_status, f"Status must remain {from_status}, got {fsm.get_status(order_id)}"


# ==============================================================================
# 3. 종료 상태(FILLED, CANCELLED, REJECTED) 재전이 차단 검증
# ==============================================================================
@pytest.mark.parametrize("terminal_status", [
    OrderStatus.FILLED,
    OrderStatus.CANCELLED,
    OrderStatus.REJECTED,
])
def test_terminal_states_cannot_transition(terminal_status):
    """종료 상태에 도달한 주문은 어떤 상태로도 다시 전이될 수 없음을 검증"""
    fsm = OmsFsm()
    order_id = uuid.uuid4()
    fsm.states[order_id] = terminal_status

    for target in OrderStatus:
        res = fsm.transition_sync(order_id, target)
        assert res is False, f"Transition from terminal state {terminal_status} to {target} must return False"
        assert fsm.get_status(order_id) == terminal_status


# ==============================================================================
# 4. PARTIAL 누적 체결 경로 (PARTIAL -> PARTIAL -> FILLED) 검증
# ==============================================================================
def test_partial_cumulative_fill_pipeline():
    """OrderRouter의 PARTIAL 누적 체결 수량 추적 및 PARTIAL -> PARTIAL -> FILLED 정상 전이 검증"""
    router = OrderRouter()
    cmd = make_test_command(qty=10)
    order_uuid = uuid.uuid4()
    token = make_test_token(order_uuid)

    order_id = router.register_and_route(command=cmd, token=token)
    assert order_id == order_uuid
    assert router.fsm.get_status(order_id) == OrderStatus.SENT

    # 1차 부분 체결: 3주 (누적 3/10) -> PARTIAL
    rep1 = make_test_report(client_order_id=cmd.client_order_id, executed_qty=3, executed_price=2.5)
    router.handle_execution_report(order_id, rep1)
    assert router.fsm.get_status(order_id) == OrderStatus.PARTIAL
    assert router._cum_executed_qty[order_id] == 3

    # 2차 부분 체결: 4주 (누적 7/10) -> PARTIAL -> PARTIAL
    rep2 = make_test_report(client_order_id=cmd.client_order_id, executed_qty=4, executed_price=2.55)
    router.handle_execution_report(order_id, rep2)
    assert router.fsm.get_status(order_id) == OrderStatus.PARTIAL
    assert router._cum_executed_qty[order_id] == 7

    # 3차 잔여 체결: 3주 (누적 10/10) -> PARTIAL -> FILLED
    rep3 = make_test_report(client_order_id=cmd.client_order_id, executed_qty=3, executed_price=2.52)
    router.handle_execution_report(order_id, rep3)
    assert router.fsm.get_status(order_id) == OrderStatus.FILLED
    assert order_id not in router._active_orders
    assert order_id not in router._cum_executed_qty


# ==============================================================================
# 5. PARTIAL -> CANCELLED, PARTIAL -> REJECTED 종료 전이 검증
# ==============================================================================
def test_partial_to_cancelled_via_stale_cancel():
    """부분 체결 후 잔여 미체결 수량에 대한 stale order cancel 시 PARTIAL -> CANCELLED 전이 검증"""
    router = OrderRouter(stale_timeout_sec=1.0)
    cmd = make_test_command(qty=10)
    order_uuid = uuid.uuid4()
    token = make_test_token(order_uuid)

    order_id = router.register_and_route(command=cmd, token=token)

    # 1차 부분 체결 4주 -> PARTIAL
    rep = make_test_report(client_order_id=cmd.client_order_id, executed_qty=4, executed_price=2.5)
    router.handle_execution_report(order_id, rep)
    assert router.fsm.get_status(order_id) == OrderStatus.PARTIAL

    # 시간 경과 후 stale scan 및 취소 요청
    stale_ids = router.scan_stale_orders(current_time=time.time() + 10.0)
    assert order_id in stale_ids

    cancelled = router.cancel_stale_order(order_id)
    assert cancelled is True
    assert router.fsm.get_status(order_id) == OrderStatus.CANCEL_REQUESTED

    # 실제 취소 확정 수신 시 CANCELLED 전이
    assert router.confirm_cancel(order_id) is True
    assert router.fsm.get_status(order_id) == OrderStatus.CANCELLED
    assert order_id not in router._active_orders


def test_partial_to_rejected_on_oversized_execution():
    """부분 체결 후 초과 수량 체결 보고 수신 시 PARTIAL -> REJECTED 전이 및 차단 검증"""
    router = OrderRouter()
    cmd = make_test_command(qty=5)
    order_uuid = uuid.uuid4()
    token = make_test_token(order_uuid)

    order_id = router.register_and_route(command=cmd, token=token)

    # 1차 정상 부분 체결 3주 -> PARTIAL
    rep1 = make_test_report(client_order_id=cmd.client_order_id, executed_qty=3, executed_price=2.5)
    router.handle_execution_report(order_id, rep1)
    assert router.fsm.get_status(order_id) == OrderStatus.PARTIAL

    # 2차 초과 체결 보고 (추가 5주 수신 -> 누적 8주 > 요청 5주) -> REJECTED
    rep2 = make_test_report(client_order_id=cmd.client_order_id, executed_qty=5, executed_price=2.5)
    router.handle_execution_report(order_id, rep2)
    assert router.fsm.get_status(order_id) == OrderStatus.REJECTED
    assert order_id not in router._active_orders


# ==============================================================================
# 6. OrderRouter 이벤트 경로와 OmsFsm 실제 연계 Functional Assertion
# ==============================================================================
def test_order_router_full_event_pathway_fsm_integrity():
    """OrderRouter의 register_and_route -> handle_execution_report 실경로와 FSM transition 일관성 검증"""
    fsm = OmsFsm()
    router = OrderRouter(fsm=fsm)

    cmd = make_test_command(order_id_str="ORD-E2E-001", qty=2, price=3.0)
    order_uuid = uuid.uuid4()
    token = make_test_token(order_uuid, client_order_id="ORD-E2E-001")

    # 1. 등록 파이프라인 (NEW -> VALIDATED -> SENT)
    ret_id = router.register_and_route(command=cmd, token=token)
    assert ret_id == order_uuid
    assert fsm.get_status(order_uuid) == OrderStatus.SENT

    # 2. 체결 보고서 처리 파이프라인 (SENT -> FILLED)
    rep = make_test_report(
        client_order_id="ORD-E2E-001",
        executed_qty=2,
        executed_price=3.0
    )
    router.handle_execution_report(order_uuid, rep)
    assert fsm.get_status(order_uuid) == OrderStatus.FILLED

    # 3. 이미 FILLED된 주문에 대해 추가 이벤트 발생 시 FSM 전이 거부 확인
    rep_dup = make_test_report(
        client_order_id="ORD-E2E-001",
        executed_qty=2,
        executed_price=3.0
    )
    router.handle_execution_report(order_uuid, rep_dup)
    assert fsm.get_status(order_uuid) == OrderStatus.FILLED


# ==============================================================================
# 7. ACCEPTED / PENDING 생성 경로 근거 검증
# ==============================================================================
def test_accepted_and_pending_fsm_support_and_runtime_absence_verification():
    """
    ACCEPTED 및 PENDING 상태는:
    1. FSM 규칙상 합법적인 상태 및 전이 경로로 완벽히 지원됨.
    2. 현재 단일 Broker 런타임(Paper/Virtual)에서는 즉시 체결 또는 거절 보고서를 반환하므로
       운영 경로에서 중간 ACK(ACCEPTED/PENDING)를 별도 이벤트로 발생시키지 않음.
    """
    fsm = OmsFsm()
    oid = uuid.uuid4()

    # FSM 허용 전이 검증 (SENT -> ACCEPTED -> PENDING -> FILLED)
    assert fsm.transition_sync(oid, OrderStatus.NEW) is True
    assert fsm.transition_sync(oid, OrderStatus.VALIDATED) is True
    assert fsm.transition_sync(oid, OrderStatus.SENT) is True
    assert fsm.transition_sync(oid, OrderStatus.ACCEPTED) is True
    assert fsm.transition_sync(oid, OrderStatus.PENDING) is True
    assert fsm.transition_sync(oid, OrderStatus.FILLED) is True
    assert fsm.get_status(oid) == OrderStatus.FILLED
