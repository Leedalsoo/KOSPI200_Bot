# -*- coding: utf-8 -*-
"""7단계-5: 부분체결·취소·거부·timeout·재시도 검증 테스트.

검증 항목:
1. 부분체결 누적 검증:
   - PARTIAL(3/10) -> PARTIAL(7/10) -> FILLED(10/10) 다회 누적 체결 정확성 및 FSM 상태 전이
   - 누적 체결 수량과 주문 요청 수량 일치성 검증
2. 부분체결 후 timeout -> 취소 검증:
   - PARTIAL 상태 주문 -> scan_stale_orders() -> 실제 Broker cancel_order() -> CANCELLED 전체 경로
3. timeout 상태 및 경계 검증:
   - SENT, ACCEPTED, PENDING, PARTIAL 4개 상태 대상
   - timeout 미만 (29.9s), timeout 정확히 동일 (30.0s), timeout 초과 (30.1s) 경계 검증
4. Broker 거부 검증:
   - executed_qty = 0 또는 거부 보고 -> REJECTED 전이
   - active order 제거, broker mapping 제거, cumulative execution 정리
5. 초과체결 검증:
   - cumulative_qty > requested_qty -> REJECTED 전이 및 내부 state 정리
6. 취소 실패 및 예외 검증:
   - Broker cancel_order()가 False 반환 시 기존 FSM 상태 및 active order 보존
   - Broker cancel_order()가 Exception 발생 시 기존 FSM 상태 및 active order 보존
7. 재시도(retry) 정책/경로 전수 확인:
   - 현재 코드상 자동 retry 정책/실행 경로 미구현 상태임을 코드/속성 수준에서 명확히 검증
8. 단대단 이벤트 경로 Functional Assertion
"""
import uuid
import time
from typing import Optional, List
import pytest
from unittest.mock import MagicMock

from shared.core.contracts import OrderStatus, RiskApprovalToken
from shared.contracts.canonical import (
    CanonicalOrderCommand,
    CanonicalExecutionReport,
    CanonicalAssetType,
    CanonicalOrderSide,
)
from option_program.orders.oms_fsm import OmsFsm
from option_program.orders.order_router import OrderRouter


def make_test_command(
    order_id_str: str = "ORD-EXC-001",
    qty: int = 10,
    price: float = 2.5,
    track_id: str = "Track1"
) -> CanonicalOrderCommand:
    return CanonicalOrderCommand(
        client_order_id=order_id_str,
        track_id=track_id,
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=qty,
        price=price,
    )


def make_test_token(
    order_uuid: uuid.UUID,
    client_order_id: str = "ORD-EXC-001",
    track_id: str = "Track1",
    custom_sig: Optional[str] = None
) -> RiskApprovalToken:
    sig = custom_sig or f"SIG-RISK-APPROVED-{track_id}-{client_order_id}"
    return RiskApprovalToken(
        order_id=order_uuid,
        timestamp_ns=time.time_ns(),
        signature=sig
    )


def make_test_report(
    client_order_id: str = "ORD-EXC-001",
    executed_qty: int = 4,
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
        timestamp="2026-08-30 09:00:00",
    )


# ==============================================================================
# 1. 부분체결 다회 누적 검증 (PARTIAL -> PARTIAL -> FILLED)
# ==============================================================================
def test_partial_execution_accumulation_path():
    """PARTIAL(3/10) -> PARTIAL(7/10) -> FILLED(10/10) 다회 누적 체결 정합성 검증"""
    router = OrderRouter()
    cmd = make_test_command(order_id_str="ORD-ACC-001", qty=10)
    order_uuid = uuid.uuid4()
    token = make_test_token(order_uuid, client_order_id="ORD-ACC-001")

    # 1. 주문 등록 (SENT)
    reg_id = router.register_and_route(command=cmd, token=token)
    assert reg_id == order_uuid
    assert router.fsm.get_status(order_uuid) == OrderStatus.SENT
    assert router._cum_executed_qty[order_uuid] == 0

    # 2. 1차 부분체결: 3개 수신 -> PARTIAL, 누적 3/10
    rep1 = make_test_report(client_order_id="ORD-ACC-001", executed_qty=3, executed_price=2.5)
    router.handle_execution_report(order_uuid, rep1)
    assert router.fsm.get_status(order_uuid) == OrderStatus.PARTIAL
    assert router._cum_executed_qty[order_uuid] == 3
    assert order_uuid in router._active_orders

    # 3. 2차 부분체결: 4개 수신 -> PARTIAL, 누적 7/10
    rep2 = make_test_report(client_order_id="ORD-ACC-001", executed_qty=4, executed_price=2.55)
    router.handle_execution_report(order_uuid, rep2)
    assert router.fsm.get_status(order_uuid) == OrderStatus.PARTIAL
    assert router._cum_executed_qty[order_uuid] == 7
    assert order_uuid in router._active_orders

    # 4. 3차 최종 체결: 3개 수신 -> FILLED, 누적 10/10 (요청수량 10과 완전 일치)
    rep3 = make_test_report(client_order_id="ORD-ACC-001", executed_qty=3, executed_price=2.6)
    router.handle_execution_report(order_uuid, rep3)
    assert router.fsm.get_status(order_uuid) == OrderStatus.FILLED
    # 체결 완료 후 active_orders 및 cum_executed_qty 정리 확인
    assert order_uuid not in router._active_orders
    assert order_uuid not in router._cum_executed_qty


# ==============================================================================
# 2. 부분체결 후 timeout -> 취소 검증
# ==============================================================================
def test_partial_then_timeout_and_cancel_path():
    """PARTIAL 상태 주문이 stale timeout에 도달하여 Broker cancel_order()를 거쳐 CANCELLED로 전이되는 전체 경로 검증"""
    router = OrderRouter(stale_timeout_sec=30.0)
    cmd = make_test_command(order_id_str="ORD-PT-001", qty=10)
    order_uuid = uuid.uuid4()
    token = make_test_token(order_uuid, client_order_id="ORD-PT-001")

    broker_mock = MagicMock()
    broker_mock.cancel_order = MagicMock(return_value=True)

    # 1. 주문 등록
    router.register_and_route(command=cmd, token=token, broker_adapter=broker_mock)
    submitted_time = router._active_orders[order_uuid][1]

    # 2. 부분체결 발생 (4/10) -> PARTIAL
    rep = make_test_report(client_order_id="ORD-PT-001", executed_qty=4, executed_price=2.5)
    router.handle_execution_report(order_uuid, rep)
    assert router.fsm.get_status(order_uuid) == OrderStatus.PARTIAL

    # 3. 30초 경과 시뮬레이션 -> scan_stale_orders() 감지
    stale_orders = router.scan_stale_orders(current_time=submitted_time + 30.1)
    assert order_uuid in stale_orders

    # 4. cancel_stale_order() 실행 (취소 요청 -> CANCEL_REQUESTED)
    success = router.cancel_stale_order(order_uuid)
    assert success is True
    broker_mock.cancel_order.assert_called_once_with("ORD-PT-001")
    assert router.fsm.get_status(order_uuid) == OrderStatus.CANCEL_REQUESTED
    assert order_uuid in router._active_orders  # 확정 전까지 active_orders 유지

    # 5. 실제 취소 확정 수신 시 CANCELLED 전이 및 active_orders 정리 검증
    confirm_ok = router.confirm_cancel(order_uuid)
    assert confirm_ok is True
    assert router.fsm.get_status(order_uuid) == OrderStatus.CANCELLED
    assert order_uuid not in router._active_orders
    assert order_uuid not in router._order_brokers
    assert order_uuid not in router._cum_executed_qty


# ==============================================================================
# 3. timeout 상태 및 경계 검증 (SENT, ACCEPTED, PENDING, PARTIAL)
# ==============================================================================
@pytest.mark.parametrize("target_status", [
    OrderStatus.SENT,
    OrderStatus.ACCEPTED,
    OrderStatus.PENDING,
    OrderStatus.PARTIAL
])
def test_stale_timeout_boundary_checks(target_status: OrderStatus):
    """
    SENT, ACCEPTED, PENDING, PARTIAL 각 상태에 대해:
    - timeout 미만 (29.9s): 미감지
    - timeout 정확히 동일 (30.0s): 감지
    - timeout 초과 (30.1s): 감지
    """
    router = OrderRouter(stale_timeout_sec=30.0)
    cmd = make_test_command(order_id_str=f"ORD-BOUND-{target_status.name}", qty=10)
    order_uuid = uuid.uuid4()
    token = make_test_token(order_uuid, client_order_id=f"ORD-BOUND-{target_status.name}")

    router.register_and_route(command=cmd, token=token)
    submitted_time = router._active_orders[order_uuid][1]

    # 대상 상태로 FSM 전이 설정
    router.fsm.transition_sync(order_uuid, target_status)
    assert router.fsm.get_status(order_uuid) == target_status

    # 경계 1: 29.9초 (timeout 미만) -> 감지되지 않아야 함
    stale_under = router.scan_stale_orders(current_time=submitted_time + 29.9)
    assert order_uuid not in stale_under

    # 경계 2: 30.0초 (timeout 정확히 일치) -> 감지되어야 함 (>= 연산자)
    stale_exact = router.scan_stale_orders(current_time=submitted_time + 30.0)
    assert order_uuid in stale_exact

    # 경계 3: 30.1초 (timeout 초과) -> 감지되어야 함
    stale_over = router.scan_stale_orders(current_time=submitted_time + 30.1)
    assert order_uuid in stale_over


# ==============================================================================
# 4. Broker 거부 검증 (executed_qty <= 0)
# ==============================================================================
def test_broker_rejection_cleans_active_state():
    """Broker 거부(executed_qty = 0) 보고 수신 시 REJECTED 전이 및 내부 state 정리 검증"""
    router = OrderRouter()
    cmd = make_test_command(order_id_str="ORD-REJ-001", qty=5)
    order_uuid = uuid.uuid4()
    token = make_test_token(order_uuid, client_order_id="ORD-REJ-001")
    broker_mock = MagicMock()

    router.register_and_route(command=cmd, token=token, broker_adapter=broker_mock)
    assert router.fsm.get_status(order_uuid) == OrderStatus.SENT

    # 거부 보고 수신 (executed_qty = 0)
    reject_report = make_test_report(client_order_id="ORD-REJ-001", executed_qty=0, executed_price=0.0)
    router.handle_execution_report(order_uuid, reject_report)

    # REJECTED 전이 및 모든 내부 리소스 정리 확인
    assert router.fsm.get_status(order_uuid) == OrderStatus.REJECTED
    assert order_uuid not in router._active_orders
    assert order_uuid not in router._order_brokers
    assert order_uuid not in router._cum_executed_qty


# ==============================================================================
# 5. 초과체결 검증 (cumulative_qty > requested_qty)
# ==============================================================================
def test_oversized_execution_rejection():
    """누적 체결수량이 주문 요청수량을 초과할 경우 REJECTED 전이 및 내부 state 정리 검증"""
    router = OrderRouter()
    cmd = make_test_command(order_id_str="ORD-OVER-001", qty=5)
    order_uuid = uuid.uuid4()
    token = make_test_token(order_uuid, client_order_id="ORD-OVER-001")

    router.register_and_route(command=cmd, token=token)

    # 1차: 4개 체결 (누적 4/5 -> PARTIAL)
    rep1 = make_test_report(client_order_id="ORD-OVER-001", executed_qty=4)
    router.handle_execution_report(order_uuid, rep1)
    assert router.fsm.get_status(order_uuid) == OrderStatus.PARTIAL

    # 2차: 추가 3개 체결 인입 (누적 7 > 요청 5 -> 초과 체결 발생)
    rep2 = make_test_report(client_order_id="ORD-OVER-001", executed_qty=3)
    router.handle_execution_report(order_uuid, rep2)

    # REJECTED 전이 및 내부 state 정리 확인
    assert router.fsm.get_status(order_uuid) == OrderStatus.REJECTED
    assert order_uuid not in router._active_orders
    assert order_uuid not in router._cum_executed_qty


# ==============================================================================
# 6. 취소 실패 및 예외 발생 시 상태 보존 검증
# ==============================================================================
def test_cancel_failure_preserves_fsm_and_active_order():
    """Broker cancel_order()가 False 반환 시 CANCELLED로 전이되지 않고 기존 상태와 active order 보존"""
    router = OrderRouter(stale_timeout_sec=30.0)
    cmd = make_test_command(order_id_str="ORD-CFAIL-001", qty=10)
    order_uuid = uuid.uuid4()
    token = make_test_token(order_uuid, client_order_id="ORD-CFAIL-001")

    broker_mock = MagicMock()
    broker_mock.cancel_order = MagicMock(return_value=False)  # 취소 실패

    router.register_and_route(command=cmd, token=token, broker_adapter=broker_mock)
    assert router.fsm.get_status(order_uuid) == OrderStatus.SENT

    # 취소 시도 -> False 반환
    success = router.cancel_stale_order(order_uuid)
    assert success is False

    # FSM 상태 SENT 유지 및 active_order 보존 확인
    assert router.fsm.get_status(order_uuid) == OrderStatus.SENT
    assert order_uuid in router._active_orders
    assert order_uuid in router._order_brokers


def test_cancel_exception_preserves_fsm_and_active_order():
    """Broker cancel_order() 중 Exception 발생 시 CANCELLED로 전이되지 않고 기존 상태와 active order 보존"""
    router = OrderRouter(stale_timeout_sec=30.0)
    cmd = make_test_command(order_id_str="ORD-CEXC-001", qty=10)
    order_uuid = uuid.uuid4()
    token = make_test_token(order_uuid, client_order_id="ORD-CEXC-001")

    broker_mock = MagicMock()
    broker_mock.cancel_order = MagicMock(side_effect=RuntimeError("Broker Network Connection Dropped"))

    router.register_and_route(command=cmd, token=token, broker_adapter=broker_mock)
    # 부분체결 상태로 설정
    rep = make_test_report(client_order_id="ORD-CEXC-001", executed_qty=3)
    router.handle_execution_report(order_uuid, rep)
    assert router.fsm.get_status(order_uuid) == OrderStatus.PARTIAL

    # 취소 시도 -> 예외 발생
    success = router.cancel_stale_order(order_uuid)
    assert success is False

    # FSM 상태 PARTIAL 유지 및 active_order 보존 확인
    assert router.fsm.get_status(order_uuid) == OrderStatus.PARTIAL
    assert order_uuid in router._active_orders
    assert router._cum_executed_qty[order_uuid] == 3


# ==============================================================================
# 7. 재시도(retry) 정책/경로 전수 확인
# ==============================================================================
def test_retry_policy_not_implemented_verification():
    """
    현재 코드베이스(OrderRouter, OmsFsm, TradingSystem)에
    자동 retry 정책/실행 경로가 미구현 상태임을 코드/속성 수준에서 명확히 검증
    """
    router = OrderRouter()
    fsm = OmsFsm()

    # 1. OrderRouter에 retry 관련 메서드 및 속성이 존재하지 않음을 확인
    assert not hasattr(router, "retry_order"), "OrderRouter에 retry_order 메서드가 없어야 함 (미구현)"
    assert not hasattr(router, "max_retries"), "OrderRouter에 max_retries 설정이 없어야 함 (미구현)"
    assert not hasattr(router, "retry_backoff_sec"), "OrderRouter에 retry_backoff_sec 설정이 없어야 함 (미구현)"

    # 2. OmsFsm에 RETRY 상태가 존재하지 않음을 확인
    status_names = [s.name for s in OrderStatus]
    assert "RETRY" not in status_names, "OrderStatus에 RETRY 상태가 없어야 함"


# ==============================================================================
# 8. 단대단 이벤트 경로 Functional Assertion
# ==============================================================================
def test_full_order_exception_lifecycle_event_path():
    """
    실제 이벤트 경로 Functional Assertion:
    주문 등록 -> 1차 부분체결 -> 타임아웃 감지 -> 브로커 취소 요청 -> FSM CANCELLED 전이
    """
    router = OrderRouter(stale_timeout_sec=30.0)
    cmd = make_test_command(order_id_str="ORD-E2E-001", qty=20, price=3.0)
    order_uuid = uuid.uuid4()
    token = make_test_token(order_uuid, client_order_id="ORD-E2E-001")

    broker_mock = MagicMock()
    broker_mock.cancel_order = MagicMock(return_value=True)

    # 1. 주문 발주 및 FSM SENT 등록
    order_id = router.register_and_route(command=cmd, token=token, broker_adapter=broker_mock)
    assert order_id == order_uuid
    assert router.fsm.get_status(order_uuid) == OrderStatus.SENT

    # 2. 거래소 부분 체결 수신 (8/20 체결)
    rep1 = make_test_report(client_order_id="ORD-E2E-001", executed_qty=8, executed_price=3.0)
    router.handle_execution_report(order_uuid, rep1)
    assert router.fsm.get_status(order_uuid) == OrderStatus.PARTIAL
    assert router._cum_executed_qty[order_uuid] == 8

    # 3. 30초 경과에 따른 Stale Order 감지
    sub_time = router._active_orders[order_uuid][1]
    stale_list = router.scan_stale_orders(current_time=sub_time + 30.5)
    assert order_uuid in stale_list

    # 4. 잔여 미체결분 취소 명령 발행
    cancel_res = router.cancel_stale_order(order_uuid)
    assert cancel_res is True
    broker_mock.cancel_order.assert_called_once_with("ORD-E2E-001")
    assert router.fsm.get_status(order_uuid) == OrderStatus.CANCEL_REQUESTED

    # 5. 실제 취소 확정 수신 시 최종 CANCELLED 전이 및 자원 정리 검증
    assert router.confirm_cancel(order_uuid) is True
    assert router.fsm.get_status(order_uuid) == OrderStatus.CANCELLED
    assert order_uuid not in router._active_orders
    assert order_uuid not in router._cum_executed_qty
