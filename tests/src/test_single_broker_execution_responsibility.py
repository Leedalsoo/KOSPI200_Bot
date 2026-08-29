"""7단계-2: 실제 TradingSystem.run_loop() 기반 단일 Broker 실행 Functional Assertion 전용 검증 테스트

검증 기준:
A. 실제 TradingSystem.run_loop()를 직접 실행 (내부 로직 수동 복제/재현 일절 금지)
B. 실제 주문 발생 강제 (generated_order_count > 0, 조건부 if 제거)
C. Broker.send_order() 실행 횟수와 생성 주문 수의 엄격한 1:1 일치 및 각 주문당 정확히 1회 실행(중복 발주 0건)
D. OptionProgramRuntime.process_tick() -> TradingSystem.run_loop() -> broker.send_order() -> consume_execution_report() -> FSM FILLED 전체 운영 경로 실측
E. ExecutionReport 수와 system.executions_handled 정합성
F. 모든 체결 완료된 주문의 OMS FSM 상태가 FILLED로 전이됨을 확인
"""
import asyncio
from unittest.mock import MagicMock
import pytest

from shared.contracts.canonical import (
    CanonicalAssetType,
    CanonicalOrderCommand,
    CanonicalOrderSide,
)
from shared.core.contracts import OrderStatus, RiskApprovalToken
from option_program.broker.broker_interface import PaperBrokerAdapter
from option_program.orders.order_router import OrderRouter
from option_program.orders.oms_fsm import OmsFsm
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


@pytest.mark.asyncio
async def test_actual_tradingsystem_run_loop_single_broker_execution_functional_assertion():
    """실제 TradingSystem.run_loop() 가동을 통한 단일 Broker 발주 및 FSM 상태 전이 Functional Assertion 실측"""
    # 1. TradingSystem 인스턴스 생성 및 초기화
    config = {"broker_mode": "PAPER", "initial_capital": 50_000_000.0}
    system = TradingSystem(config)
    await system.initialize()

    assert system.vms is not None
    assert system.vssf is not None
    assert system.broker is not None
    assert system.op_runtime is not None

    # 2. Broker.send_order 및 consume_execution_report 호출 감시용 spy wrapping
    real_send_order = system.broker.send_order
    spy_broker_send = MagicMock(side_effect=real_send_order)
    system.broker.send_order = spy_broker_send

    real_consume = system.op_runtime.consume_execution_report
    spy_consume_report = MagicMock(side_effect=real_consume)
    system.op_runtime.consume_execution_report = spy_consume_report

    # 3. [핵심 A] 실제 TradingSystem.run_loop() 직접 가동 (내부 로직 수동 복제 없음)
    max_ticks_to_run = 10
    await system.run_loop(max_ticks=max_ticks_to_run)

    # 4. [핵심 B] 주문 발생 강제 및 검증 (조건부 if 제거, > 0 assert)
    generated_order_count = system.orders_routed
    assert generated_order_count > 0, "TradingSystem must generate at least 1 order during run_loop"
    assert system.ticks_processed == max_ticks_to_run

    # 5. [핵심 C] Broker 실행 횟수와 생성 주문 수 엄격 일치 및 중복 발주 0건 검증
    assert spy_broker_send.call_count == generated_order_count, (
        f"Broker.send_order must be called exactly once per generated order: "
        f"expected {generated_order_count}, got {spy_broker_send.call_count}"
    )

    # 각 주문당 send_order 정확히 1회 호출 여부 전수 검증
    order_id_call_counts = {}
    for call_item in spy_broker_send.call_args_list:
        called_cmd = call_item[0][0]
        cid = called_cmd.client_order_id
        order_id_call_counts[cid] = order_id_call_counts.get(cid, 0) + 1

    assert len(order_id_call_counts) == generated_order_count, "All generated orders must have unique client_order_id"
    for cid, count in order_id_call_counts.items():
        assert count == 1, f"Order {cid} was called {count} times (must be exactly 1, no duplicates)"

    # 6. [핵심 D, E] ExecutionReport 생성, consume_execution_report 경로 및 정합성 검증
    assert system.executions_handled > 0, "At least 1 execution report must be generated and handled"
    assert spy_consume_report.call_count == system.executions_handled, (
        f"consume_execution_report call count ({spy_consume_report.call_count}) must match executions_handled ({system.executions_handled})"
    )
    assert len(system.op_runtime.received_execution_reports) == system.executions_handled, (
        "All handled execution reports must be safely stored in op_runtime.received_execution_reports"
    )

    # 7. [핵심 F] 체결된 주문의 OMS FSM 상태가 FILLED로 전이되었음을 실측 검증
    for report in system.op_runtime.received_execution_reports:
        order_uuid = system.op_runtime._order_id_to_uuid.get(report.client_order_id)
        assert order_uuid is not None, f"Order UUID mapping must exist for client_order_id: {report.client_order_id}"
        fsm_status = system.op_runtime.oms_fsm.get_status(order_uuid)
        assert fsm_status == OrderStatus.FILLED, (
            f"Order {report.client_order_id} (UUID: {order_uuid}) must be in FILLED state, got {fsm_status}"
        )

    # 8. 사후 리소스 정리
    await system.shutdown()
