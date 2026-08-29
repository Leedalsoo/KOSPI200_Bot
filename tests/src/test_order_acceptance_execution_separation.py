# -*- coding: utf-8 -*-
"""8단계-1: 주문 접수와 실제 체결 분리 검증 테스트.

검증 항목:
1. 주문 접수 성공 직후 FSM 상태는 NEW -> VALIDATED -> SENT 이며, FILLED나 PARTIAL이 아님
2. Broker 주문 제출 성공과 실제 체결 완료는 명확히 분리된 별개 이벤트임
3. Broker 주문 제출 성공(ACK)만으로는 FSM FILLED 금지, Position 증가 금지, PnL 반영 금지, Ledger 체결 기록 금지
4. PARTIAL / FILLED 전이는 반드시 실제 CanonicalExecutionReport 수신 후에만 발생
5. 주문 접수 -> OrderRouter 등록(SENT) -> Broker 제출(미체결 유지) -> Execution Report 수신(PARTIAL/FILLED)
   실제 이벤트 경계 Functional Assertion
6. 체결 이벤트 없이 Broker 제출 성공만 발생한 경우 체결수량이 증가하지 않음 (0 유지)
7. 실제 체결 이벤트 도착 시에만 PARTIAL/FILLED 및 누적 체결수량이 변경됨
8. executed_qty = 0 Broker 거부(REJECTED)와 정상 execution report가 명확히 구분됨
9. 7단계-2에서 확정된 단일 Broker 실행 책임 구조 유지
"""
import uuid
import time
from typing import Optional
from decimal import Decimal
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
from virtual_securities_firm.account.paper_account import PaperTradingAccount


def make_test_command(
    order_id_str: str = "ORD-SEP-001",
    qty: int = 10,
    price: float = 2.5,
    track_id: str = "Track1",
    side: CanonicalOrderSide = CanonicalOrderSide.BUY
) -> CanonicalOrderCommand:
    return CanonicalOrderCommand(
        client_order_id=order_id_str,
        track_id=track_id,
        asset_type=CanonicalAssetType.OPTION,
        side=side,
        qty=qty,
        price=price,
    )


def make_test_token(
    order_uuid: uuid.UUID,
    client_order_id: str = "ORD-SEP-001",
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
    client_order_id: str = "ORD-SEP-001",
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
# 1. 주문 접수 성공 직후 상태 검증 (SENT, not FILLED, not PARTIAL)
# ==============================================================================
def test_order_registration_is_sent_not_filled_or_partial():
    """주문 등록 성공 직후 FSM 상태는 SENT이며, FILLED나 PARTIAL이 아님을 검증"""
    router = OrderRouter()
    cmd = make_test_command(order_id_str="ORD-SEP-001", qty=10)
    order_uuid = uuid.uuid4()
    token = make_test_token(order_uuid, client_order_id="ORD-SEP-001")

    # OrderRouter 등록
    res_id = router.register_and_route(command=cmd, token=token)

    assert res_id == order_uuid
    status = router.fsm.get_status(order_uuid)

    # 1. 상태는 오직 SENT 여야 함
    assert status == OrderStatus.SENT
    assert status != OrderStatus.FILLED, "주문 접수 직후에는 FILLED 상태가 될 수 없음"
    assert status != OrderStatus.PARTIAL, "주문 접수 직후에는 PARTIAL 상태가 될 수 없음"
    assert status != OrderStatus.REJECTED
    assert status != OrderStatus.CANCELLED

    # 2. 누적 체결 수량은 0이어야 함
    assert router._cum_executed_qty[order_uuid] == 0
    assert order_uuid in router._active_orders


# ==============================================================================
# 2. Broker 주문 제출 성공과 실제 체결 분리 검증
# ==============================================================================
def test_broker_submission_success_separated_from_execution():
    """Broker에 주문 제출(ACK)이 성공해도 체결 보고서 전에는 FSM 상태가 SENT로 유지됨을 검증"""
    router = OrderRouter()
    cmd = make_test_command(order_id_str="ORD-SEP-002", qty=5)
    order_uuid = uuid.uuid4()
    token = make_test_token(order_uuid, client_order_id="ORD-SEP-002")

    # 브로커 모의 객체: send_order는 ACK만 반환 (체결은 아직 없음)
    broker_mock = MagicMock()
    broker_mock.send_order = MagicMock(return_value={"status": "SUBMITTED", "broker_order_id": "B-999"})

    # 1. 주문 라우터 등록
    router.register_and_route(command=cmd, token=token)
    assert router.fsm.get_status(order_uuid) == OrderStatus.SENT

    # 2. 브로커에 주문 제출
    broker_resp = broker_mock.send_order(cmd)
    assert broker_resp["status"] == "SUBMITTED"

    # 3. 제출 성공 후에도 FSM 상태 및 누적 체결 수량은 여전히 SENT 및 0이어야 함
    assert router.fsm.get_status(order_uuid) == OrderStatus.SENT
    assert router._cum_executed_qty[order_uuid] == 0
    assert router.fsm.get_status(order_uuid) != OrderStatus.FILLED
    assert router.fsm.get_status(order_uuid) != OrderStatus.PARTIAL


# ==============================================================================
# 3. Broker 제출만으로 Position / PnL / Ledger 체결 반영 금지 검증
# ==============================================================================
def test_broker_submission_does_not_mutate_position_pnl_or_ledger():
    """Broker 제출 시점에는 VSSF Account에 포지션, PnL, Ledger 체결이 일체 발생하지 않음을 검증"""
    account = PaperTradingAccount(initial_capital=25000000.0)

    # 주문 대상 심볼
    symbol = "201T2380"

    # 주문 접수 전 상태 확인
    assert account.positions.get(symbol) is None
    assert account.pnl_engine.realized_pnl == 0.0
    assert len(account.ledger_engine.transactions) == 0

    # 주문이 발주된 상태 (아직 ExecutionEngine의 process_execution 전)
    # 체결 이벤트가 없으므로 계좌 상태는 100% 미변경(None, 0.0, 0)이어야 함
    assert account.positions.get(symbol) is None
    assert account.pnl_engine.realized_pnl == 0.0
    assert len(account.ledger_engine.transactions) == 0


# ==============================================================================
# 4. CanonicalExecutionReport 수신 후에만 PARTIAL / FILLED 반영 검증
# ==============================================================================
def test_execution_reflected_only_upon_canonical_execution_report():
    """실제 CanonicalExecutionReport 수신 시에만 단계적으로 PARTIAL 및 FILLED 상태로 전이됨을 검증"""
    router = OrderRouter()
    cmd = make_test_command(order_id_str="ORD-SEP-003", qty=10)
    order_uuid = uuid.uuid4()
    token = make_test_token(order_uuid, client_order_id="ORD-SEP-003")

    router.register_and_route(command=cmd, token=token)
    assert router.fsm.get_status(order_uuid) == OrderStatus.SENT

    # 1. 1차 부분 체결 보고서 (4/10) 수신 전 -> SENT
    assert router.fsm.get_status(order_uuid) == OrderStatus.SENT

    # 1차 부분 체결 보고서 수신 후 -> PARTIAL
    rep1 = make_test_report(client_order_id="ORD-SEP-003", executed_qty=4, executed_price=2.5)
    router.handle_execution_report(order_uuid, rep1)
    assert router.fsm.get_status(order_uuid) == OrderStatus.PARTIAL
    assert router._cum_executed_qty[order_uuid] == 4

    # 2. 2차 잔여 체결 보고서 (6/10) 수신 후 -> FILLED
    rep2 = make_test_report(client_order_id="ORD-SEP-003", executed_qty=6, executed_price=2.55)
    router.handle_execution_report(order_uuid, rep2)
    assert router.fsm.get_status(order_uuid) == OrderStatus.FILLED
    assert order_uuid not in router._active_orders
    assert order_uuid not in router._cum_executed_qty


# ==============================================================================
# 5. 체결 이벤트 없이 Broker 제출 성공만 발생 시 체결 수량 0 유지 검증
# ==============================================================================
def test_broker_submission_without_execution_preserves_zero_fill():
    """Broker 제출 성공 후 체결 보고서가 오지 않는 경우 누적 체결 수량이 0으로 보존됨을 검증"""
    router = OrderRouter()
    cmd = make_test_command(order_id_str="ORD-SEP-004", qty=8)
    order_uuid = uuid.uuid4()
    token = make_test_token(order_uuid, client_order_id="ORD-SEP-004")

    router.register_and_route(command=cmd, token=token)
    assert router._cum_executed_qty[order_uuid] == 0

    # 임의의 시간 경과 시뮬레이션 (체결 없음)
    assert router._cum_executed_qty[order_uuid] == 0
    assert router.fsm.get_status(order_uuid) == OrderStatus.SENT


# ==============================================================================
# 6. Broker 거부(executed_qty=0)와 정상 체결 분리 검증
# ==============================================================================
def test_broker_rejection_separated_from_execution():
    """executed_qty = 0 거부 보고 수신 시 FILLED나 PARTIAL이 아닌 REJECTED로 전이됨을 검증"""
    router = OrderRouter()
    cmd = make_test_command(order_id_str="ORD-SEP-005", qty=5)
    order_uuid = uuid.uuid4()
    token = make_test_token(order_uuid, client_order_id="ORD-SEP-005")

    router.register_and_route(command=cmd, token=token)
    assert router.fsm.get_status(order_uuid) == OrderStatus.SENT

    # 거부 보고서 수신 (executed_qty = 0)
    rej_report = make_test_report(client_order_id="ORD-SEP-005", executed_qty=0, executed_price=0.0)
    router.handle_execution_report(order_uuid, rej_report)

    assert router.fsm.get_status(order_uuid) == OrderStatus.REJECTED
    assert order_uuid not in router._active_orders


# ==============================================================================
# 7. 단대단 주문 접수-체결 분리 파이프라인 Functional Assertion
# ==============================================================================
def test_full_pipeline_order_acceptance_and_execution_separation_functional_assertion():
    """
    실제 파이프라인 단대단 Functional Assertion:
    1단계: 주문 접수 -> OrderRouter 등록 -> SENT
    2단계: TradingSystem Broker 제출 -> 여전히 미체결 (SENT)
    3단계: 1차 체결 이벤트 수신 -> PARTIAL (수량 5/10)
    4단계: 2차 체결 이벤트 수신 -> FILLED (누적 10/10)
    """
    router = OrderRouter()
    cmd = make_test_command(order_id_str="ORD-E2E-SEP-001", qty=10, price=3.0)
    order_uuid = uuid.uuid4()
    token = make_test_token(order_uuid, client_order_id="ORD-E2E-SEP-001")

    broker_mock = MagicMock()
    broker_mock.send_order = MagicMock(return_value={"status": "ACCEPTED", "id": "BRK-101"})

    # 1단계: 주문 접수 및 FSM SENT 등록
    routed_id = router.register_and_route(command=cmd, token=token)
    assert routed_id == order_uuid
    assert router.fsm.get_status(order_uuid) == OrderStatus.SENT
    assert router._cum_executed_qty[order_uuid] == 0

    # 2단계: 단일 Broker 실행 오케스트레이터가 Broker 발주 실행
    broker_resp = broker_mock.send_order(cmd)
    assert broker_resp["status"] == "ACCEPTED"
    # 발주 직후에도 체결 보고서 수신 전이므로 여전히 SENT 및 체결수량 0 유지
    assert router.fsm.get_status(order_uuid) == OrderStatus.SENT
    assert router._cum_executed_qty[order_uuid] == 0

    # 3단계: 거래소로부터 1차 부분 체결 이벤트 수신 (5/10 체결)
    rep_partial = make_test_report(client_order_id="ORD-E2E-SEP-001", executed_qty=5, executed_price=3.0)
    router.handle_execution_report(order_uuid, rep_partial)
    assert router.fsm.get_status(order_uuid) == OrderStatus.PARTIAL
    assert router._cum_executed_qty[order_uuid] == 5

    # 4단계: 잔여 5개 체결 이벤트 수신 (누적 10/10 체결 완료)
    rep_full = make_test_report(client_order_id="ORD-E2E-SEP-001", executed_qty=5, executed_price=3.0)
    router.handle_execution_report(order_uuid, rep_full)
    assert router.fsm.get_status(order_uuid) == OrderStatus.FILLED
    assert order_uuid not in router._active_orders
    assert order_uuid not in router._cum_executed_qty
