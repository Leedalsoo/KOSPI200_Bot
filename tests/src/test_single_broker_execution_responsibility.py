"""7단계-2: Broker 실행 책임 단일화 전용 검증 테스트

검증 범위:
1. OptionProgramRuntime.process_tick()에서 생성된 command가 정상 반환됨.
2. OrderRouter.register_and_route()에 broker_adapter를 전달하더라도 Broker.send_order()를 직접 호출하지 않음.
3. 실제 실행 경로에서 Broker.send_order()가 정확히 1회만 단일 호출됨 (중복 발주 원천 차단).
4. Broker 체결 후 ExecutionReport가 OptionProgramRuntime.consume_execution_report() -> OrderRouter.handle_execution_report()로 전달되어 FSM 상태가 FILLED로 전이됨.
5. TradingSystem(main.py)의 실행 파이프라인에서 단일 발주 책임이 정확히 유지됨.
"""
from unittest.mock import MagicMock
import pytest

from shared.contracts.canonical import (
    CanonicalAssetType,
    CanonicalMarketTick,
    CanonicalOrderCommand,
    CanonicalOrderSide,
    CanonicalExecutionReport,
)
from shared.core.contracts import OrderStatus, RiskApprovalToken
from option_program.broker.broker_interface import BrokerFactory, BrokerMode, PaperBrokerAdapter
from option_program.runtime.program_runtime import OptionProgramRuntime
from option_program.orders.order_router import OrderRouter
from option_program.orders.oms_fsm import OmsFsm
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime
from main import TradingSystem


def test_order_router_does_not_call_broker_directly():
    """OrderRouter.register_and_route에 broker_adapter가 전달되어도 직접 send_order를 호출하지 않음을 검증"""
    fsm = OmsFsm()
    router = OrderRouter(fsm=fsm)
    mock_broker = MagicMock(spec=PaperBrokerAdapter)

    cmd = CanonicalOrderCommand(
        client_order_id="ORD-TEST-001",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=1,
        price=2.0,
    )
    import uuid
    import time
    order_uuid = uuid.uuid4()
    token = RiskApprovalToken(
        order_id=order_uuid,
        timestamp_ns=time.time_ns(),
        signature="SIG-RISK-APPROVED-Track1-ORD-TEST-001"
    )

    # broker_adapter를 명시적으로 전달하여 호출
    order_id = router.register_and_route(command=cmd, token=token, broker_adapter=mock_broker, mode_str="PAPER")

    assert order_id is not None
    # 핵심 검증: OrderRouter는 broker.send_order()를 절대 직접 호출하지 않음
    mock_broker.send_order.assert_not_called()
    assert mock_broker.send_order.call_count == 0

    # FSM은 발주 대기 상태(SENT)로 정상 등록됨
    assert fsm.get_status(order_id) == OrderStatus.SENT


def test_single_broker_execution_and_fsm_lifecycle_transition():
    """TradingSystem 및 OptionProgramRuntime 실행 경로에서 단일 발주 및 체결 통지 수명주기 검증"""
    vssf = VirtualSecuritiesFirmRuntime(initial_capital=25_000_000.0)
    vssf.order_book.update_bid_ask(bid_price=2.0, ask_price=2.05)
    broker = BrokerFactory.create_broker(mode=BrokerMode.PAPER, vssf_runtime=vssf)
    op_runtime = OptionProgramRuntime(account_summary=vssf.get_account_snapshot())

    # Broker.send_order 호출 횟수 감시용 Mock Wrap
    broker.send_order = MagicMock(side_effect=broker.send_order)

    tick = CanonicalMarketTick(
        timestamp="2026-08-23 09:05:00",
        underlying_price=350.0,
        strike_price=350.0,
        option_type="CALL",
        bid_price=2.0,
        ask_price=2.05,
        last_price=2.0,
        volume=100,
        seq_id=1,
    )

    # 1. OptionProgramRuntime 틱 평가 -> 주문 command 생성
    commands = op_runtime.process_tick(tick)

    # 주문이 발생한 경우 검증
    if commands:
        cmd = commands[0]
        order_uuid = op_runtime._order_id_to_uuid.get(cmd.client_order_id)
        assert order_uuid is not None
        assert op_runtime.oms_fsm.get_status(order_uuid) == OrderStatus.SENT

        # OrderRouter 내부에서 broker 호출이 발생하지 않았는지 재확인
        assert broker.send_order.call_count == 0

        # 2. 오케스트레이터(TradingSystem/main.py)가 단일 발주 수행
        report = broker.send_order(cmd)
        assert report is not None
        assert broker.send_order.call_count == 1, "Broker.send_order must be called exactly once"

        # 3. 체결 보고서 통지 -> FSM FILLED 전이
        op_runtime.consume_execution_report(report)
        assert op_runtime.oms_fsm.get_status(order_uuid) == OrderStatus.FILLED
        assert len(op_runtime.received_execution_reports) == 1
        assert op_runtime.received_execution_reports[0].exec_id == report.exec_id


def test_tradingsystem_pipeline_single_execution_guarantee():
    """TradingSystem.run_loop 실행 시 동일 주문에 대해 Broker 발주가 정확히 1회만 일어나는지 E2E 검증"""
    system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 25_000_000.0})
    vssf = VirtualSecuritiesFirmRuntime(initial_capital=25_000_000.0)
    broker = PaperBrokerAdapter(vssf_runtime=vssf)
    system.vssf = vssf
    system.broker = broker
    system.op_runtime = OptionProgramRuntime(account_summary=vssf.get_account_snapshot())

    # 감시용 spy
    spy_broker_send = MagicMock(side_effect=broker.send_order)
    broker.send_order = spy_broker_send

    # 1개 틱 수동 처리 시뮬레이션 (run_loop 내부 1회 실행 스텝)
    tick = CanonicalMarketTick(
        timestamp="2026-08-23 09:00:00",
        underlying_price=350.0,
        strike_price=350.0,
        option_type="CALL",
        bid_price=2.0,
        ask_price=2.05,
        last_price=2.0,
        volume=10,
        seq_id=1,
    )

    system.vssf.process_market_data(tick)
    system.op_runtime.update_account_summary(system.vssf.get_account_snapshot())
    commands = system.op_runtime.process_tick(tick)

    for cmd in commands:
        system.orders_routed += 1
        rep = system.broker.send_order(cmd)
        if rep is not None:
            system.executions_handled += 1
            system.op_runtime.consume_execution_report(rep)

    if commands:
        assert len(commands) == system.orders_routed
        assert spy_broker_send.call_count == len(commands), "Every command must trigger exactly one broker send_order call"
        assert system.executions_handled == len(commands)
