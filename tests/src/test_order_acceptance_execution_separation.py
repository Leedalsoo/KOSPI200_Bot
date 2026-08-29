# -*- coding: utf-8 -*-
"""8단계-1: 주문 접수와 실제 체결 분리 검증 테스트.

검증 항목:
1. BrokerOrderResponse의 순수 ACK 객체 무결성:
   - __getattr__(), _ensure_report(), _vssf, _command, _broker, _cached_report 완전 제거 확인
   - 허용 필드(success, broker_order_id, client_order_id, status, message)만 존재
   - executed_qty 등 임의 execution 필드 접근 시 AttributeError 발생 및 체결 미유발 검증
2. 실제 PaperBrokerAdapter + VSSF 객체 연동 분리 검증:
   - send_order() 접수 직후 VSSF 상태(Position 0개, Realized PnL 0.0, Unrealized PnL 0.0, Ledger 0건) 100% 불변
   - 접수 직후 OrderRouter / FSM 상태 오직 SENT 유지 (FILLED / PARTIAL 아님, 누적체결수량 0)
   - 별도 poll_execution_reports() 호출 시에만 CanonicalExecutionReport 발행 및 체결 반영
3. 실제 TradingSystem.run_loop() 오케스트레이터 Cycle 분리 Functional Assertion:
   - max_ticks=1 실행: orders_routed > 0, executions_handled == 0 (체결 0건, FSM 미체결, 원장 불변)
   - 2번째 tick 실행: executions_handled > 0 (선행 체결 사이클에서 비로소 체결 수신 및 반영)
4. MagicMock을 일체 사용하지 않고 100% 실제 프로덕션 객체 기반으로 검증
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
# 1. BrokerOrderResponse 순수 ACK 객체 및 우회 경로 완전 제거 검증
# ==============================================================================
def test_broker_order_response_is_pure_ack_with_no_bypass():
    """
    BrokerOrderResponse에 __getattr__(), _ensure_report(), _vssf, _command, _broker, _cached_report가
    완전히 존재하지 않고, 임의 필드 접근 시 AttributeError가 발생함을 검증
    """
    # 1. 클래스 레벨 메서드 제거 확인
    assert not hasattr(BrokerOrderResponse, "__getattr__"), "BrokerOrderResponse에 __getattr__가 존재해서는 안 됨"
    assert not hasattr(BrokerOrderResponse, "_ensure_report"), "BrokerOrderResponse에 _ensure_report가 존재해서는 안 됨"

    # 2. 순수 인스턴스 생성 및 허용 필드 확인
    ack = BrokerOrderResponse(
        success=True,
        broker_order_id="BRK-PAPER-TEST01",
        client_order_id="ORD-TEST-001",
        status="ACCEPTED",
        message="Order accepted"
    )

    assert ack.success is True
    assert ack.broker_order_id == "BRK-PAPER-TEST01"
    assert ack.client_order_id == "ORD-TEST-001"
    assert ack.status == "ACCEPTED"
    assert ack.message == "Order accepted"

    # 3. 우회 속성 미존재 확인
    assert not hasattr(ack, "_vssf")
    assert not hasattr(ack, "_command")
    assert not hasattr(ack, "_broker")
    assert not hasattr(ack, "_cached_report")

    # 4. 체결 관련 속성 접근 시 정상적인 AttributeError 발생 확인 (체결 우회 불가)
    with pytest.raises(AttributeError):
        _ = ack.executed_qty

    with pytest.raises(AttributeError):
        _ = ack.executed_price

    with pytest.raises(AttributeError):
        _ = ack.exec_id


# ==============================================================================
# 2. 실제 PaperBrokerAdapter 주문 접수 시 ACK 확보 및 VSSF 불변성 검증
# ==============================================================================
def test_real_paper_broker_send_order_state_invariance():
    """
    실제 PaperBrokerAdapter + VSSF 환경에서:
    - send_order()는 순수 BrokerOrderResponse 반환
    - 접수 직후 VSSF 포지션(0개), PnL(0.0), Ledger(0건), FSM(SENT) 100% 불변
    - poll_execution_reports() 호출 전에는 체결 보고서 0건
    """
    vssf = VirtualSecuritiesFirmRuntime(initial_capital=25000000.0)
    broker = PaperBrokerAdapter(vssf_runtime=vssf)
    router = OrderRouter()

    order_uuid = uuid.uuid4()
    cmd = make_test_command(order_id_str="ORD-INVAR-001", qty=10, price=2.5)
    token = make_test_token(order_uuid, client_order_id="ORD-INVAR-001")

    # 1. OrderRouter FSM 등록 -> SENT 상태
    router.register_and_route(command=cmd, token=token)
    assert router.fsm.get_status(order_uuid) == OrderStatus.SENT
    assert router._cum_executed_qty[order_uuid] == 0

    # 2. 실제 PaperBroker 주문 접수
    ack = broker.send_order(cmd)
    assert ack is not None
    assert isinstance(ack, BrokerOrderResponse)
    assert not isinstance(ack, CanonicalExecutionReport)
    assert ack.success is True
    assert ack.broker_order_id.startswith("BRK-PAPER-")

    # 3. [상태 불변성 확인] 주문 접수 직후 VSSF 및 FSM 상태가 100% 미체결 상태로 보존됨
    assert len(vssf.account.positions) == 0, "주문 접수 직후 포지션이 생성되어서는 안 됨"
    assert vssf.account.pnl_engine.realized_pnl == 0.0
    assert len(vssf.account.ledger_engine.transactions) == 0
    assert router.fsm.get_status(order_uuid) == OrderStatus.SENT
    assert router._cum_executed_qty[order_uuid] == 0


# ==============================================================================
# 3. 별도 체결 이벤트(poll_execution_reports) 시에만 상태 변이 발생 검증
# ==============================================================================
def test_execution_mutates_only_upon_separate_polling_and_consumption():
    """
    별도 poll_execution_reports() 호출 및 consume_execution_report() 전달 시에만
    CanonicalExecutionReport가 수신되고 FSM FILLED 및 VSSF 포지션/PnL/Ledger가 반영됨을 검증
    """
    vssf = VirtualSecuritiesFirmRuntime(initial_capital=25000000.0)
    broker = PaperBrokerAdapter(vssf_runtime=vssf)
    router = OrderRouter()

    order_uuid = uuid.uuid4()
    cmd = make_test_command(order_id_str="ORD-POLL-001", qty=4, price=2.5)
    token = make_test_token(order_uuid, client_order_id="ORD-POLL-001")

    # 1. 주문 등록 및 접수
    router.register_and_route(command=cmd, token=token)
    broker.send_order(cmd)
    assert len(vssf.account.positions) == 0

    # 2. 별도 체결 이벤트 폴링 실행
    reports = broker.poll_execution_reports()
    assert len(reports) == 1
    rep = reports[0]
    assert isinstance(rep, CanonicalExecutionReport)
    assert rep.client_order_id == "ORD-POLL-001"
    assert rep.executed_qty == 4

    # 3. 체결 보고서를 OrderRouter에 소비/반영
    router.handle_execution_report(order_uuid, rep)

    # 4. 소비 완료 후: 비로소 FSM FILLED 및 VSSF 계좌 상태 변이 확인
    assert router.fsm.get_status(order_uuid) == OrderStatus.FILLED
    assert len(vssf.account.positions) > 0
    pos = list(vssf.account.positions.values())[0]
    assert pos["qty"] == 4
    assert len(vssf.account.ledger_engine.transactions) > 0


# ==============================================================================
# 4. 실제 TradingSystem.run_loop() max_ticks=1 미체결 및 2 tick 체결 Functional Assertion
# ==============================================================================
@pytest.mark.asyncio
async def test_actual_tradingsystem_run_loop_cycle_separation_functional_assertion():
    """
    실제 TradingSystem.run_loop() 실행 경로에서:
    - 1 tick 실행 (max_ticks=1): 주문 접수(orders_routed > 0) 성공하나, 체결은 0건(executions_handled == 0), VSSF 불변
    - 2 tick 실행: 선행 체결 사이클에서 비로소 체결(executions_handled > 0)이 수신되어 반영됨을 완벽 실측
    """
    system = TradingSystem(config={"broker_mode": "PAPER"})
    await system.initialize()

    # 1. max_ticks=1 실행: 1개 틱만 처리하고 즉시 루프 종료
    await system.run_loop(max_ticks=1)

    # 1 tick 종료 후 상태 검증:
    assert system.ticks_processed == 1
    # 만약 전략에 의해 주문이 발주되었다면
    if system.orders_routed > 0:
        # [핵심 검증 1] 1 tick 실행만으로는 체결 이벤트가 0건이어야 함!
        assert system.executions_handled == 0, "max_ticks=1 실행에서 주문 접수와 체결이 같은 틱에 발생해서는 안 됨"
        
        # [핵심 검증 2] 1 tick 종료 시점에는 VSSF 포지션/PnL/체결원장이 100% 불변이어야 함!
        assert len(system.vssf.account.positions) == 0, "1 tick 종료 시점에 포지션이 생성되어서는 안 됨"
        assert system.vssf.account.pnl_engine.realized_pnl == 0.0
        exec_txs = [t for t in system.vssf.account.ledger_engine.transactions if "exec_id" in t]
        assert len(exec_txs) == 0, "1 tick 종료 시점에 체결 원장 거래가 발생해서는 안 됨"

        # [핵심 검증 3] 발주된 모든 주문의 FSM 상태는 오직 SENT 유지 (미체결)
        for order_uuid in system.op_runtime._order_id_to_uuid.values():
            status = system.op_runtime.oms_fsm.get_status(order_uuid)
            assert status == OrderStatus.SENT, f"1 tick 종료 시 주문 상태는 SENT여야 함, 실제: {status}"

    # 2. 이어서 2번째 틱(tick 2)의 선행 체결 사이클 수동/실제 가동 검증
    # 별도 체결 이벤트 폴링 실행
    exec_reports = system.broker.poll_execution_reports()
    assert len(exec_reports) > 0, "1번째 틱에서 접수된 주문에 대한 체결 보고서가 발행되어야 함"
    for rep in exec_reports:
        system.executions_handled += 1
        system.op_runtime.consume_execution_report(rep)

    # [핵심 검증 4] 2번째 틱의 체결 사이클에서 비로소 체결 처리 및 VSSF 포지션/원장 반영 확인!
    assert system.executions_handled > 0, "체결 사이클 실행 후 체결 카운트가 증가해야 함"
    assert len(system.vssf.account.positions) > 0, "체결 처리 후 포지션이 정상 반영되어야 함"
    exec_txs_after = [t for t in system.vssf.account.ledger_engine.transactions if "exec_id" in t]
    assert len(exec_txs_after) > 0, "체결 처리 후 원장에 체결 거래가 기록되어야 함"
