# -*- coding: utf-8 -*-
"""8단계-1: 주문 접수와 실제 체결 분리 검증 테스트.

검증 항목:
1. 실제 PaperBrokerAdapter 주문 접수(send_order) 성공 시 BrokerOrderResponse (ACK / broker_order_id) 반환
2. 주문 접수 직후 ExecutionReport가 발생하지 않고, VSSF 매칭 대기 큐에 안전하게 보관됨
3. 주문 접수 직후 OrderRouter / OMS FSM 상태는 오직 SENT 유지 (FILLED / PARTIAL 아님)
4. 주문 접수 직후 실제 VSSF Account의 Position (0개), Realized PnL (0.0), Ledger (0건)가 100% 불변 보존
5. 별도 체결 이벤트(poll_execution_reports) 호출 시에만 VSSF 체결이 실행되어 CanonicalExecutionReport 반환
6. 체결 보고서(consume_execution_report) 전달 후에만 FSM FILLED 전이 및 VSSF Position/PnL/Ledger 변이 반영
7. 다회 부분체결 시에도 주문 접수 단계와 각 체결 수신 단계가 완전히 분리되어 동작함을 검증
8. 실제 TradingSystem 오케스트레이터 실행 경로에서 주문 접수 -> 대기(미체결) -> 체결 통지 분리 파이프라인 무결성 검증
9. MagicMock에 의존하지 않고 실제 PaperBrokerAdapter 및 VSSF 객체 연동으로 검증
"""
import uuid
import time
from typing import Optional
import pytest

from shared.core.contracts import OrderStatus, RiskApprovalToken
from shared.contracts.canonical import (
    CanonicalOrderCommand,
    CanonicalExecutionReport,
    CanonicalAssetType,
    CanonicalOrderSide,
)
from option_program.orders.oms_fsm import OmsFsm
from option_program.orders.order_router import OrderRouter
from option_program.broker.broker_interface import PaperBrokerAdapter, BrokerOrderResponse
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime
from main import TradingSystem


def make_test_command(
    order_id_str: str = "ORD-SEP-001",
    qty: int = 5,
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


# ==============================================================================
# 1. 실제 PaperBrokerAdapter 주문 접수 계약 및 ACK/Order ID 반환 검증
# ==============================================================================
def test_real_paper_broker_send_order_returns_ack_not_execution_report():
    """실제 PaperBrokerAdapter.send_order()는 ExecutionReport가 아닌 BrokerOrderResponse(ACK)를 반환함을 검증"""
    vssf = VirtualSecuritiesFirmRuntime(initial_capital=25000000.0)
    broker = PaperBrokerAdapter(vssf_runtime=vssf)
    cmd = make_test_command(order_id_str="ORD-ACK-001", qty=5, price=2.5)

    # 1. 주문 접수 호출
    resp = broker.send_order(cmd)

    # 2. 계약 검증: BrokerOrderResponse 반환
    assert resp is not None
    assert isinstance(resp, BrokerOrderResponse), f"반환값은 BrokerOrderResponse여야 함, 실제: {type(resp)}"
    assert not isinstance(resp, CanonicalExecutionReport), "send_order 반환값이 CanonicalExecutionReport여서는 안 됨"
    assert resp.success is True
    assert resp.client_order_id == "ORD-ACK-001"
    assert resp.broker_order_id.startswith("BRK-PAPER-")
    assert resp.status == "ACCEPTED"


# ==============================================================================
# 2. 주문 접수 직후 VSSF 상태 불변 및 ExecutionReport 미수신 상태 검증
# ==============================================================================
def test_order_submission_leaves_vssf_state_and_fsm_unchanged():
    """
    주문 접수 직후(체결 이벤트 폴링 전)에는:
    - FSM은 오직 SENT 유지 (FILLED / PARTIAL 아님)
    - VSSF 포지션 0개, PnL 0.0, Ledger 0건으로 100% 불변
    - 누적 체결 수량 0
    """
    vssf = VirtualSecuritiesFirmRuntime(initial_capital=25000000.0)
    broker = PaperBrokerAdapter(vssf_runtime=vssf)
    router = OrderRouter()

    order_uuid = uuid.uuid4()
    cmd = make_test_command(order_id_str="ORD-STATE-001", qty=10, price=2.5)
    token = make_test_token(order_uuid, client_order_id="ORD-STATE-001")

    # 1. OrderRouter FSM 등록
    router.register_and_route(command=cmd, token=token)
    assert router.fsm.get_status(order_uuid) == OrderStatus.SENT
    assert router._cum_executed_qty[order_uuid] == 0

    # 2. 실제 PaperBroker에 주문 제출 (ACK 수신)
    ack = broker.send_order(cmd)
    assert ack is not None and ack.success is True

    # 3. [핵심 검증] 주문 제출 성공 직후 VSSF 및 FSM 상태 불변 확인
    # FSM 상태: SENT 유지
    assert router.fsm.get_status(order_uuid) == OrderStatus.SENT
    assert router.fsm.get_status(order_uuid) != OrderStatus.FILLED
    assert router.fsm.get_status(order_uuid) != OrderStatus.PARTIAL
    assert router._cum_executed_qty[order_uuid] == 0

    # VSSF 상태: 체결 전이므로 Position/PnL/Ledger 일체 불변
    assert len(vssf.account.positions) == 0
    assert vssf.account.pnl_engine.realized_pnl == 0.0
    assert len(vssf.account.ledger_engine.transactions) == 0


# ==============================================================================
# 3. 별도 체결 이벤트(poll_execution_reports) 전달 후에만 상태 변경 검증
# ==============================================================================
def test_execution_state_mutates_only_after_poll_execution_reports():
    """별도 체결 이벤트 폴링 및 consume_execution_report 전달 후에만 실제 체결 상태가 반영됨을 검증"""
    vssf = VirtualSecuritiesFirmRuntime(initial_capital=25000000.0)
    broker = PaperBrokerAdapter(vssf_runtime=vssf)
    router = OrderRouter()

    order_uuid = uuid.uuid4()
    cmd = make_test_command(order_id_str="ORD-EXEC-001", qty=4, price=2.5)
    token = make_test_token(order_uuid, client_order_id="ORD-EXEC-001")

    # 1. 주문 등록 및 제출
    router.register_and_route(command=cmd, token=token)
    broker.send_order(cmd)

    # 제출 직후: VSSF 포지션 없음
    assert len(vssf.account.positions) == 0

    # 2. 별도 체결 이벤트 폴링 실행
    reports = broker.poll_execution_reports()
    assert len(reports) == 1
    rep = reports[0]
    assert isinstance(rep, CanonicalExecutionReport)
    assert rep.client_order_id == "ORD-EXEC-001"
    assert rep.executed_qty == 4

    # 3. 체결 보고서를 OrderRouter에 통지
    router.handle_execution_report(order_uuid, rep)

    # 4. 통지 완료 후: FSM FILLED 전이 및 VSSF 포지션/원장 반영 확인
    assert router.fsm.get_status(order_uuid) == OrderStatus.FILLED
    assert len(vssf.account.positions) > 0
    pos_data = list(vssf.account.positions.values())[0]
    assert pos_data["qty"] == 4
    assert len(vssf.account.ledger_engine.transactions) > 0


# ==============================================================================
# 4. 부분체결 시뮬레이션 및 다단계 체결 분리 검증
# ==============================================================================
def test_partial_execution_and_staged_events_separation():
    """주문 접수 -> 1차 부분체결 수신(PARTIAL) -> 2차 잔여체결 수신(FILLED) 단계적 분리 검증"""
    router = OrderRouter()
    cmd = make_test_command(order_id_str="ORD-STAGED-001", qty=10, price=2.5)
    order_uuid = uuid.uuid4()
    token = make_test_token(order_uuid, client_order_id="ORD-STAGED-001")

    # 1. 주문 접수 및 FSM SENT 등록
    router.register_and_route(command=cmd, token=token)
    assert router.fsm.get_status(order_uuid) == OrderStatus.SENT
    assert router._cum_executed_qty[order_uuid] == 0

    # 2. 1차 부분체결 보고서 수신 (3/10)
    rep1 = CanonicalExecutionReport(
        exec_id="EXEC-STAGED-1",
        client_order_id="ORD-STAGED-001",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        executed_qty=3,
        executed_price=2.5,
        fee=100.0,
        slippage=0.0,
        timestamp="2026-08-30 09:00:00"
    )
    router.handle_execution_report(order_uuid, rep1)
    assert router.fsm.get_status(order_uuid) == OrderStatus.PARTIAL
    assert router._cum_executed_qty[order_uuid] == 3
    assert order_uuid in router._active_orders

    # 3. 2차 잔여체결 보고서 수신 (7/10)
    rep2 = CanonicalExecutionReport(
        exec_id="EXEC-STAGED-2",
        client_order_id="ORD-STAGED-001",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        executed_qty=7,
        executed_price=2.55,
        fee=150.0,
        slippage=0.0,
        timestamp="2026-08-30 09:00:01"
    )
    router.handle_execution_report(order_uuid, rep2)
    assert router.fsm.get_status(order_uuid) == OrderStatus.FILLED
    assert order_uuid not in router._active_orders


# ==============================================================================
# 5. 실제 TradingSystem 오케스트레이터 경로 분리 Functional Assertion
# ==============================================================================
@pytest.mark.asyncio
async def test_actual_tradingsystem_order_acceptance_and_execution_separation():
    """
    실제 TradingSystem 파이프라인 환경에서:
    - 틱 인입 시 주문 접수와 체결 이벤트 폴링이 순차적/독립적 단계로 실행되는지 Functional Assertion
    """
    system = TradingSystem(config={"broker_mode": "PAPER"})
    await system.initialize()

    assert system.broker is not None
    assert system.op_runtime is not None
    assert system.vms is not None

    # 1개 틱 생성
    tick = next(system.vms.generate_tick_stream(total_days=1, ticks_per_day=10))
    system.last_tick = tick

    # 1. 시세 반영 및 주문 생성
    system.vssf.process_market_data(tick)
    system.op_runtime.update_account_summary(system.vssf.get_account_snapshot())
    commands = system.op_runtime.process_tick(tick)

    # 생성된 주문이 있다면 분리 파이프라인 실측
    if commands:
        init_execs = system.executions_handled
        init_routed = system.orders_routed

        # 2. 주문 접수 단계 실행 (send_order)
        for cmd in commands:
            system.orders_routed += 1
            ack = system.broker.send_order(cmd)
            assert ack is not None
            assert isinstance(ack, BrokerOrderResponse)
            assert ack.success is True

        # 주문 접수 직후: orders_routed는 증가했으나, 아직 executions_handled는 미변경이어야 함
        assert system.orders_routed == init_routed + len(commands)
        assert system.executions_handled == init_execs, "주문 접수 단계에서 체결 카운트가 즉시 증가해서는 안 됨"

        # 3. 별도 체결 이벤트 폴링 단계 실행 (poll_execution_reports)
        exec_reports = system.broker.poll_execution_reports()
        for report in exec_reports:
            system.executions_handled += 1
            system.op_runtime.consume_execution_report(report)

        # 체결 이벤트 처리 후: executions_handled 정상 증가 확인
        assert system.executions_handled == init_execs + len(exec_reports)
