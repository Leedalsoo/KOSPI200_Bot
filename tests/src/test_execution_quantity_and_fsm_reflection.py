"""[8단계-3] 상태조회/체결 이벤트 -> 실제 체결수량 반영 및 FSM 상태 전이 검증.

검증 항목:
1. poll_execution_reports() 체결 이벤트가 Runtime 소비 경로(consume_execution_report)로 정상 전달
2. 체결 이벤트가 정확한 내부 주문에 귀속 (client_order_id 직접 매핑 및 broker_order_id 역추적 매핑)
3. executed_qty가 주문 추적 권위 상태(OrderRouter)에 실제 반영 (get_executed_qty 조회 일치성)
4. 체결 후 기존 FSM 상태 갱신 (단일/전량 체결 -> FILLED, 부분 체결 -> PARTIAL, 초과 체결 -> REJECTED, 비정상 수량 -> REJECTED)
5. 8단계-2 broker_order_id 매핑과 체결 주문 식별 연결
6. ACK와 실제 체결 분리 유지 (send_order 직후에는 체결 0건, poll_execution_reports 소비 후 반영)
7. 실제 TradingSystem.run_loop() 단대단 실행 시 체결 수량 및 FSM 상태 갱신 실측
"""
import pytest
import uuid
from datetime import datetime

from shared.contracts.canonical import (
    CanonicalOrderCommand,
    CanonicalExecutionReport,
    CanonicalAssetType,
    CanonicalOrderSide,
    CanonicalOptionType,
)
from shared.core.contracts import OrderStatus, RiskApprovalToken
from option_program.broker.broker_interface import (
    BrokerOrderResponse,
    PaperBrokerAdapter,
)
from option_program.broker.real_broker_adapter import RealBrokerAdapter, RealBrokerConfig
from option_program.orders.order_router import OrderRouter
from option_program.orders.oms_fsm import OmsFsm
from option_program.runtime.program_runtime import OptionProgramRuntime
from main import TradingSystem


def _make_dummy_command(client_order_id: str, qty: int = 10, price: float = 350.0) -> CanonicalOrderCommand:
    return CanonicalOrderCommand(
        client_order_id=client_order_id,
        track_id="Track1",
        asset_type=CanonicalAssetType.FUTURES,
        side=CanonicalOrderSide.BUY,
        qty=qty,
        price=price,
        symbol="KOSPI200",
    )


def test_execution_report_attribution_by_client_and_broker_order_id():
    """[검증 1, 2, 5] CanonicalExecutionReport가 client_order_id 및 broker_order_id 역추적으로 정확한 내부 주문에 귀속됨을 검증."""
    runtime = OptionProgramRuntime()
    fsm = runtime.oms_fsm
    router = runtime.order_router

    # 1. 주문 생성 및 Router 등록
    client_id_1 = "ORD-ATTR-CLIENT-01"
    order_uuid_1 = uuid.uuid4()
    cmd_1 = _make_dummy_command(client_id_1, qty=5)
    token_1 = RiskApprovalToken(order_id=order_uuid_1, timestamp_ns=1000, signature=f"SIG-RISK-APPROVED-Track1-{client_id_1}")
    router.register_and_route(cmd_1, token_1)
    runtime._order_id_to_uuid[client_id_1] = order_uuid_1

    # 2. Broker ACK 모사 및 매핑 등록
    broker_id_1 = "BRK-PAPER-ATTR-01"
    ack_1 = BrokerOrderResponse(success=True, broker_order_id=broker_id_1, client_order_id=client_id_1)
    runtime.register_broker_order_ack(ack_1)

    # 3. client_order_id 기반 체결 이벤트 수신
    rep_1 = CanonicalExecutionReport(
        exec_id="EXEC-ATTR-01",
        client_order_id=client_id_1,
        track_id="Track1",
        asset_type=CanonicalAssetType.FUTURES,
        side=CanonicalOrderSide.BUY,
        executed_qty=5,
        executed_price=350.0,
        fee=1000.0,
        slippage=0.0,
        timestamp="2026-08-30 09:00:00",
    )
    runtime.consume_execution_report(rep_1)

    # 체결 귀속 및 수량/FSM 반영 확인
    assert fsm.get_status(order_uuid_1) == OrderStatus.FILLED
    assert router.get_executed_qty(order_uuid_1) == 5
    assert runtime.get_order_executed_qty(client_id_1) == 5

    # 4. client_order_id가 누락되고 broker_order_id만 포함된 체결 이벤트 수신 (역추적 귀속)
    client_id_2 = "ORD-ATTR-BROKER-02"
    order_uuid_2 = uuid.uuid4()
    cmd_2 = _make_dummy_command(client_id_2, qty=3)
    token_2 = RiskApprovalToken(order_id=order_uuid_2, timestamp_ns=2000, signature=f"SIG-RISK-APPROVED-Track1-{client_id_2}")
    router.register_and_route(cmd_2, token_2)
    runtime._order_id_to_uuid[client_id_2] = order_uuid_2

    broker_id_2 = "BRK-REAL-ATTR-02"
    ack_2 = BrokerOrderResponse(success=True, broker_order_id=broker_id_2, client_order_id=client_id_2)
    runtime.register_broker_order_ack(ack_2)

    # client_order_id="" 이고 broker_order_id가 있는 체결 보고서
    class ExecutionReportWithBrokerId:
        def __init__(self):
            self.exec_id = "EXEC-ATTR-02"
            self.client_order_id = ""
            self.broker_order_id = broker_id_2
            self.track_id = "Track1"
            self.asset_type = CanonicalAssetType.FUTURES
            self.side = CanonicalOrderSide.BUY
            self.executed_qty = 3
            self.executed_price = 350.0
            self.fee = 1000.0
            self.slippage = 0.0
            self.timestamp = "2026-08-30 09:00:00"

    rep_2 = ExecutionReportWithBrokerId()
    runtime.consume_execution_report(rep_2)

    # broker_order_id 역추적을 통한 체결 귀속 및 수량/FSM 반영 확인
    assert fsm.get_status(order_uuid_2) == OrderStatus.FILLED
    assert router.get_executed_qty(order_uuid_2) == 3
    assert runtime.get_order_executed_qty(client_id_2) == 3


def test_partial_then_full_fill_quantity_and_fsm_progression():
    """[검증 3, 4] 부분체결(PARTIAL) -> 누적체결(FILLED) 시 실제 executed_qty 반영 및 FSM 상태 전이 검증."""
    runtime = OptionProgramRuntime()
    fsm = runtime.oms_fsm
    router = runtime.order_router

    client_id = "ORD-PARTIAL-FILL-01"
    order_uuid = uuid.uuid4()
    total_qty = 10
    cmd = _make_dummy_command(client_id, qty=total_qty)
    token = RiskApprovalToken(order_id=order_uuid, timestamp_ns=3000, signature=f"SIG-RISK-APPROVED-Track1-{client_id}")
    router.register_and_route(cmd, token)
    runtime._order_id_to_uuid[client_id] = order_uuid

    # 등록 초기 상태 확인
    assert fsm.get_status(order_uuid) == OrderStatus.SENT
    assert router.get_executed_qty(order_uuid) == 0
    assert runtime.get_order_executed_qty(client_id) == 0

    # 1. 1차 부분 체결: 4계약 체결
    rep_part1 = CanonicalExecutionReport(
        exec_id="EXEC-P-01",
        client_order_id=client_id,
        track_id="Track1",
        asset_type=CanonicalAssetType.FUTURES,
        side=CanonicalOrderSide.BUY,
        executed_qty=4,
        executed_price=350.0,
        fee=400.0,
        slippage=0.0,
        timestamp="2026-08-30 09:00:01",
    )
    runtime.consume_execution_report(rep_part1)

    assert fsm.get_status(order_uuid) == OrderStatus.PARTIAL
    assert router.get_executed_qty(order_uuid) == 4
    assert runtime.get_order_executed_qty(client_id) == 4

    # 2. 2차 부분 체결: 추가 3계약 체결 (누적 7계약)
    rep_part2 = CanonicalExecutionReport(
        exec_id="EXEC-P-02",
        client_order_id=client_id,
        track_id="Track1",
        asset_type=CanonicalAssetType.FUTURES,
        side=CanonicalOrderSide.BUY,
        executed_qty=3,
        executed_price=350.0,
        fee=300.0,
        slippage=0.0,
        timestamp="2026-08-30 09:00:02",
    )
    runtime.consume_execution_report(rep_part2)

    assert fsm.get_status(order_uuid) == OrderStatus.PARTIAL
    assert router.get_executed_qty(order_uuid) == 7
    assert runtime.get_order_executed_qty(client_id) == 7

    # 3. 3차 최종 잔량 체결: 추가 3계약 체결 (누적 10계약 -> 전량 체결)
    rep_full = CanonicalExecutionReport(
        exec_id="EXEC-P-03",
        client_order_id=client_id,
        track_id="Track1",
        asset_type=CanonicalAssetType.FUTURES,
        side=CanonicalOrderSide.BUY,
        executed_qty=3,
        executed_price=350.0,
        fee=300.0,
        slippage=0.0,
        timestamp="2026-08-30 09:00:03",
    )
    runtime.consume_execution_report(rep_full)

    assert fsm.get_status(order_uuid) == OrderStatus.FILLED
    assert router.get_executed_qty(order_uuid) == 10
    assert runtime.get_order_executed_qty(client_id) == 10


def test_oversized_and_invalid_execution_fsm_rejection():
    """[검증 4-2] 초과 체결 및 비정상 수량 체결 시 FSM REJECTED 전이 검증."""
    runtime = OptionProgramRuntime()
    fsm = runtime.oms_fsm
    router = runtime.order_router

    # 1. 초과 체결 케이스 (주문 5계약인데 체결 6계약 도착)
    client_id_over = "ORD-OVERSIZED-01"
    order_uuid_over = uuid.uuid4()
    cmd_over = _make_dummy_command(client_id_over, qty=5)
    token_over = RiskApprovalToken(order_id=order_uuid_over, timestamp_ns=4000, signature=f"SIG-RISK-APPROVED-Track1-{client_id_over}")
    router.register_and_route(cmd_over, token_over)
    runtime._order_id_to_uuid[client_id_over] = order_uuid_over

    rep_over = CanonicalExecutionReport(
        exec_id="EXEC-OVER-01",
        client_order_id=client_id_over,
        track_id="Track1",
        asset_type=CanonicalAssetType.FUTURES,
        side=CanonicalOrderSide.BUY,
        executed_qty=6,  # 초과
        executed_price=350.0,
        fee=600.0,
        slippage=0.0,
        timestamp="2026-08-30 09:00:01",
    )
    runtime.consume_execution_report(rep_over)
    assert fsm.get_status(order_uuid_over) == OrderStatus.REJECTED

    # 2. 비정상 수량 케이스 (executed_qty <= 0)
    client_id_zero = "ORD-ZERO-QTY-01"
    order_uuid_zero = uuid.uuid4()
    cmd_zero = _make_dummy_command(client_id_zero, qty=5)
    token_zero = RiskApprovalToken(order_id=order_uuid_zero, timestamp_ns=5000, signature=f"SIG-RISK-APPROVED-Track1-{client_id_zero}")
    router.register_and_route(cmd_zero, token_zero)
    runtime._order_id_to_uuid[client_id_zero] = order_uuid_zero

    rep_zero = CanonicalExecutionReport(
        exec_id="EXEC-ZERO-01",
        client_order_id=client_id_zero,
        track_id="Track1",
        asset_type=CanonicalAssetType.FUTURES,
        side=CanonicalOrderSide.BUY,
        executed_qty=0,  # 0 이하
        executed_price=350.0,
        fee=0.0,
        slippage=0.0,
        timestamp="2026-08-30 09:00:01",
    )
    runtime.consume_execution_report(rep_zero)
    assert fsm.get_status(order_uuid_zero) == OrderStatus.REJECTED


@pytest.mark.asyncio
async def test_actual_tradingsystem_run_loop_executed_qty_and_fsm_functional_assertion():
    """[검증 6, 7] 실제 TradingSystem.run_loop() 단대단 실행 시 체결 수량 및 FSM 상태 갱신 실측."""
    system = TradingSystem(config={"broker_mode": "PAPER"})
    await system.initialize()

    # 1. 1틱 실행 (주문 접수 ACK 확보 및 체결 대기 큐 적재)
    await system.run_loop(max_ticks=1)

    assert system.ticks_processed == 1
    if system.orders_routed > 0:
        # 1틱 종료 시점에는 체결 처리 전이므로 체결수량 0 및 FSM SENT 유지
        for client_id, order_uuid in system.op_runtime._order_id_to_uuid.items():
            assert system.op_runtime.get_order_executed_qty(client_id) == 0
            assert system.op_runtime.oms_fsm.get_status(order_uuid) == OrderStatus.SENT

        # 2. 2번째 틱의 선행 체결 사이클 실행 (poll_execution_reports -> consume_execution_report)
        exec_reports = system.broker.poll_execution_reports()
        assert len(exec_reports) > 0, "체결 보고서가 1건 이상 존재해야 함"
        for rep in exec_reports:
            system.op_runtime.consume_execution_report(rep)

        # 3. 체결 소비 후 실제 executed_qty 반영 및 FSM FILLED 전이 확인
        for rep in exec_reports:
            client_id = rep.client_order_id
            order_uuid = system.op_runtime._order_id_to_uuid[client_id]
            assert system.op_runtime.get_order_executed_qty(client_id) == rep.executed_qty
            assert system.op_runtime.order_router.get_executed_qty(order_uuid) == rep.executed_qty
            assert system.op_runtime.oms_fsm.get_status(order_uuid) == OrderStatus.FILLED
