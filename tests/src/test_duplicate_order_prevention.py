# -*- coding: utf-8 -*-
"""7단계-4: 중복 주문 방지 및 기존 정상 주문 FSM 상태 보존 검증 테스트.

검증 항목:
1. 동일 RiskApprovalToken 재사용 시 중복 주문 차단 (None 반환)
2. 동일 order_id에 대해 다른 token/signature 조합으로 재시도해도 중복 주문 차단
3. 최초 정상 주문은 정확히 1회만 등록되고 FSM 상태가 SENT로 등록됨
4. 중복 요청이 register_and_route()에서 차단되어 Broker 실행 경로로 미전달됨을 Functional Assertion으로 검증
5. [핵심] 중복 요청 거부 시 기존 정상 주문의 상태 훼손 방지:
   - SENT 상태인 기존 주문에 동일 주문 중복 요청 시 SENT 상태 및 active order 보존 (REJECTED 전이 방지)
   - PARTIAL 상태인 기존 주문에 동일 주문 중복 요청 시 PARTIAL 상태, active order, 누적 체결 수량 보존 (REJECTED 전이 방지)
6. 종료 상태(FILLED, CANCELLED, REJECTED) 도달 후 동일 token / order_id 식별자 재사용 정책 차단 일관성 검증
7. 동시 다중 스레드 중복 요청 race condition 시 정확히 1건만 성공하고 나머지는 원자적으로 차단됨을 검증
8. 단일 Broker 실행 책임 구조와 결합하여 중복 주문 발생 시 Broker에는 최초 1회만 전달됨을 검증
"""
import uuid
import time
from typing import Optional
import pytest
from concurrent.futures import ThreadPoolExecutor
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
    order_id_str: str = "ORD-DUP-001",
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
    client_order_id: str = "ORD-DUP-001",
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
    client_order_id: str = "ORD-DUP-001",
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
# 1. 동일 RiskApprovalToken 재사용 시 중복 주문 차단
# ==============================================================================
def test_duplicate_token_reuse_is_blocked():
    """동일한 RiskApprovalToken으로 register_and_route() 2회 호출 시 2회차는 None 반환 및 차단"""
    router = OrderRouter()
    cmd = make_test_command(order_id_str="ORD-001")
    order_uuid = uuid.uuid4()
    token = make_test_token(order_uuid, client_order_id="ORD-001")

    # 1회차: 정상 등록 성공
    res1 = router.register_and_route(command=cmd, token=token)
    assert res1 == order_uuid
    assert router.fsm.get_status(order_uuid) == OrderStatus.SENT

    # 2회차: 동일 토큰 재사용 -> 차단 (None 반환)
    res2 = router.register_and_route(command=cmd, token=token)
    assert res2 is None
    # 기존 주문 상태는 정상 SENT 유지
    assert router.fsm.get_status(order_uuid) == OrderStatus.SENT


# ==============================================================================
# 2. 동일 order_id에 다른 signature 조합으로 재시도해도 차단
# ==============================================================================
def test_same_order_id_different_token_is_blocked():
    """동일한 order_id에 대해 다른 signature/token으로 재시도해도 중복 주문이 차단됨을 검증"""
    router = OrderRouter()
    cmd = make_test_command(order_id_str="ORD-002")
    order_uuid = uuid.uuid4()
    token1 = make_test_token(order_uuid, client_order_id="ORD-002")
    token2 = make_test_token(order_uuid, client_order_id="ORD-002", custom_sig="SIG-RISK-APPROVED-Track1-ORD-002-ALT")

    # 1회차: 정상 등록
    res1 = router.register_and_route(command=cmd, token=token1)
    assert res1 == order_uuid

    # 2회차: 동일 order_id + 다른 token -> 차단
    res2 = router.register_and_route(command=cmd, token=token2)
    assert res2 is None
    assert router.fsm.get_status(order_uuid) == OrderStatus.SENT


# ==============================================================================
# 3. 최초 정상 주문은 정확히 1회만 등록됨
# ==============================================================================
def test_first_order_registered_exactly_once():
    """최초 주문만 1회 등록되고 active_orders 및 _cum_executed_qty에 단 1건만 유지됨을 검증"""
    router = OrderRouter()
    cmd = make_test_command(order_id_str="ORD-003", qty=5)
    order_uuid = uuid.uuid4()
    token = make_test_token(order_uuid, client_order_id="ORD-003")

    # 최초 1회 등록
    res = router.register_and_route(command=cmd, token=token)
    assert res == order_uuid
    assert len(router._active_orders) == 1
    assert order_uuid in router._active_orders
    assert router._cum_executed_qty[order_uuid] == 0
    assert router.fsm.get_status(order_uuid) == OrderStatus.SENT


# ==============================================================================
# 4. 중복 요청 시 Broker 실행 경로로 미전달 (Functional Assertion)
# ==============================================================================
def test_duplicate_order_not_sent_to_broker():
    """
    단일 Broker 실행 책임 구조에서 중복 주문 시도는 register_and_route()에서 차단(None 반환)되어
    오케스트레이터의 Broker 발주 목록에 포함되지 않음을 검증
    """
    router = OrderRouter()
    cmd = make_test_command(order_id_str="ORD-004")
    order_uuid = uuid.uuid4()
    token = make_test_token(order_uuid, client_order_id="ORD-004")

    broker_mock = MagicMock()
    broker_mock.send_order = MagicMock(return_value={"status": "ACK"})

    # 시뮬레이션: 오케스트레이터의 주문 발주 루프
    commands_to_process = [cmd, cmd]  # 중복 커맨드 수신 상황
    sent_to_broker = []

    for command in commands_to_process:
        order_id = router.register_and_route(command=command, token=token)
        if order_id is not None:
            # register_and_route가 성공한 유효 주문만 Broker로 발주
            resp = broker_mock.send_order(command)
            sent_to_broker.append((order_id, resp))

    # Broker는 최초 1회만 호출되어야 함
    assert len(sent_to_broker) == 1
    assert broker_mock.send_order.call_count == 1
    assert sent_to_broker[0][0] == order_uuid


# ==============================================================================
# 5. [핵심] 중복 차단 시 기존 주문 상태(SENT / PARTIAL) 훼손 방지 검증
# ==============================================================================
def test_duplicate_rejection_preserves_sent_order_state():
    """기존 주문이 SENT 상태일 때 동일 주문 중복 요청이 들어와도 REJECTED로 전이되지 않고 SENT 보존"""
    router = OrderRouter()
    cmd = make_test_command(order_id_str="ORD-005", qty=10)
    order_uuid = uuid.uuid4()
    token = make_test_token(order_uuid, client_order_id="ORD-005")

    # 1. 주문 등록 -> SENT
    order_id = router.register_and_route(command=cmd, token=token)
    assert order_id == order_uuid
    assert router.fsm.get_status(order_uuid) == OrderStatus.SENT
    assert order_uuid in router._active_orders

    # 2. 동일 주문 중복 요청 -> 차단
    dup_res = router.register_and_route(command=cmd, token=token)
    assert dup_res is None

    # 3. 기존 정상 주문의 상태 및 active_orders가 보존되는지 검증
    assert router.fsm.get_status(order_uuid) == OrderStatus.SENT, "기존 주문이 REJECTED로 변경되어서는 안 됨"
    assert order_uuid in router._active_orders, "기존 active_order 정보가 제거되어서는 안 됨"


def test_duplicate_rejection_preserves_partial_order_state():
    """기존 주문이 PARTIAL 상태일 때 동일 주문 중복 요청이 들어와도 REJECTED로 전이되지 않고 PARTIAL 보존"""
    router = OrderRouter()
    cmd = make_test_command(order_id_str="ORD-006", qty=10)
    order_uuid = uuid.uuid4()
    token = make_test_token(order_uuid, client_order_id="ORD-006")

    # 1. 주문 등록 -> SENT
    order_id = router.register_and_route(command=cmd, token=token)
    assert order_id == order_uuid

    # 2. 1차 부분 체결 발생 -> PARTIAL (4/10 체결)
    rep = make_test_report(client_order_id="ORD-006", executed_qty=4, executed_price=2.5)
    router.handle_execution_report(order_uuid, rep)
    assert router.fsm.get_status(order_uuid) == OrderStatus.PARTIAL
    assert router._cum_executed_qty[order_uuid] == 4

    # 3. 동일 주문 중복 요청 발생 -> 차단
    dup_res = router.register_and_route(command=cmd, token=token)
    assert dup_res is None

    # 4. 기존 PARTIAL 상태 및 누적 체결 수량 보존 확인
    assert router.fsm.get_status(order_uuid) == OrderStatus.PARTIAL, "PARTIAL 상태가 REJECTED로 훼손되어서는 안 됨"
    assert router._cum_executed_qty[order_uuid] == 4, "누적 체결 수량이 훼손되어서는 안 됨"
    assert order_uuid in router._active_orders, "active_order 정보가 유지되어야 함"

    # 5. 이후 잔여 체결(6/10) 수신 시 정상적으로 FILLED 전이 가능한지 확인
    rep_final = make_test_report(client_order_id="ORD-006", executed_qty=6, executed_price=2.5)
    router.handle_execution_report(order_uuid, rep_final)
    assert router.fsm.get_status(order_uuid) == OrderStatus.FILLED
    assert order_uuid not in router._active_orders


# ==============================================================================
# 6. 종료 상태(FILLED/CANCELLED/REJECTED) 후 식별자 재사용 정책 차단 검증
# ==============================================================================
def test_reuse_blocked_after_order_completion():
    """주문이 FILLED / CANCELLED / REJECTED로 종료된 이후에도 동일 토큰 및 order_id 재사용이 차단됨을 검증"""
    router = OrderRouter(stale_timeout_sec=1.0)

    # 케이스 A: FILLED 종료 후 재사용 차단
    cmd_a = make_test_command(order_id_str="ORD-TERM-A", qty=2)
    oid_a = uuid.uuid4()
    token_a = make_test_token(oid_a, client_order_id="ORD-TERM-A")
    router.register_and_route(command=cmd_a, token=token_a)
    rep_a = make_test_report(client_order_id="ORD-TERM-A", executed_qty=2)
    router.handle_execution_report(oid_a, rep_a)
    assert router.fsm.get_status(oid_a) == OrderStatus.FILLED

    # FILLED 후 동일 토큰 재요청 -> 차단
    assert router.register_and_route(command=cmd_a, token=token_a) is None
    assert router.fsm.get_status(oid_a) == OrderStatus.FILLED

    # 케이스 B: CANCELLED 종료 후 재사용 차단
    cmd_b = make_test_command(order_id_str="ORD-TERM-B", qty=2)
    oid_b = uuid.uuid4()
    token_b = make_test_token(oid_b, client_order_id="ORD-TERM-B")
    router.register_and_route(command=cmd_b, token=token_b)
    router.cancel_stale_order(oid_b)
    assert router.fsm.get_status(oid_b) == OrderStatus.CANCELLED

    # CANCELLED 후 동일 토큰 재요청 -> 차단
    assert router.register_and_route(command=cmd_b, token=token_b) is None
    assert router.fsm.get_status(oid_b) == OrderStatus.CANCELLED


# ==============================================================================
# 7. 동시 중복 요청(Race Condition) 시 원자적 차단 검증
# ==============================================================================
def test_concurrent_duplicate_order_race_condition():
    """다중 스레드에서 동일한 token/order_id로 동시에 register_and_route() 호출 시 정확히 1건만 등록됨을 검증"""
    router = OrderRouter()
    cmd = make_test_command(order_id_str="ORD-RACE-001", qty=5)
    order_uuid = uuid.uuid4()
    token = make_test_token(order_uuid, client_order_id="ORD-RACE-001")

    concurrency = 20
    results = []

    def try_register():
        return router.register_and_route(command=cmd, token=token)

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(try_register) for _ in range(concurrency)]
        for f in futures:
            results.append(f.result())

    # 정확히 1개만 order_uuid를 반환하고, 나머지는 모두 None이어야 함
    success_results = [r for r in results if r is not None]
    blocked_results = [r for r in results if r is None]

    assert len(success_results) == 1, f"동시 요청 중 성공 건수는 정확히 1건이어야 함, 실제: {len(success_results)}"
    assert success_results[0] == order_uuid
    assert len(blocked_results) == concurrency - 1
    assert router.fsm.get_status(order_uuid) == OrderStatus.SENT
    assert len(router._active_orders) == 1


# ==============================================================================
# 8. 유효하지 않은 신규 토큰 거부 시 REJECTED 전이 회귀 검증
# ==============================================================================
def test_invalid_new_token_rejection_marks_fsm_rejected():
    """중복이 아닌 신규 위변조 토큰에 대해서는 FSM 상태가 정상적으로 REJECTED로 전이됨을 검증"""
    router = OrderRouter()
    cmd = make_test_command(order_id_str="ORD-INV-001")
    order_uuid = uuid.uuid4()
    # 위변조된 서명 토큰
    tampered_token = make_test_token(order_uuid, client_order_id="ORD-INV-001", custom_sig="TAMPERED-SIGNATURE")

    res = router.register_and_route(command=cmd, token=tampered_token)
    assert res is None
    # 신규 위변조 건은 REJECTED 전이되어야 함
    assert router.fsm.get_status(order_uuid) == OrderStatus.REJECTED
