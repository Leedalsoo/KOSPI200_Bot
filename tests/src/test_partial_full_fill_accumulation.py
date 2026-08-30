"""[8단계-4] Partial/Full fill 누적 검증 전용 테스트.

검증 시나리오 (8종 전수 검증):
1. 주문수량 10: 4 → 3 → 3 = 누적 10, PARTIAL → PARTIAL → FILLED
2. 주문수량 10: 단일 10 = FILLED
3. 주문수량 10: 2 → 2 → 6 = FILLED
4. 주문수량 10: 4 → 5 = 누적 9, PARTIAL 유지
5. 주문수량 10: 6 → 5 = 누적 11, 초과 체결 REJECTED 규칙 확인
6. executed_qty 0 및 음수 체결 시 REJECTED 규칙 확인
7. broker_order_id 역추적을 통한 체결 귀속 및 누적 체결 회귀 확인
8. ACK 직후 executed_qty 0 / FSM SENT 유지, 체결 이벤트 소비 후에만 누적수량 및 FSM 변화 확인
"""
import pytest
import uuid

from shared.contracts.canonical import (
    CanonicalOrderCommand,
    CanonicalExecutionReport,
    CanonicalAssetType,
    CanonicalOrderSide,
)
from shared.core.contracts import OrderStatus, RiskApprovalToken
from option_program.broker.broker_interface import (
    BrokerOrderResponse,
    PaperBrokerAdapter,
)
from option_program.orders.oms_fsm import OmsFsm
from option_program.runtime.program_runtime import OptionProgramRuntime
from main import TradingSystem


def _setup_order(runtime: OptionProgramRuntime, client_id: str, qty: int = 10, price: float = 350.0) -> uuid.UUID:
    """테스트용 주문 등록 헬퍼."""
    order_uuid = uuid.uuid4()
    cmd = CanonicalOrderCommand(
        client_order_id=client_id,
        track_id="Track1",
        asset_type=CanonicalAssetType.FUTURES,
        side=CanonicalOrderSide.BUY,
        qty=qty,
        price=price,
        symbol="KOSPI200",
    )
    token = RiskApprovalToken(
        order_id=order_uuid,
        timestamp_ns=1000000,
        signature=f"SIG-RISK-APPROVED-Track1-{client_id}",
    )
    runtime.order_router.register_and_route(cmd, token)
    runtime._order_id_to_uuid[client_id] = order_uuid
    return order_uuid


def _make_exec_report(client_id: str, exec_id: str, qty: int, price: float = 350.0) -> CanonicalExecutionReport:
    """체결 보고서 생성 헬퍼."""
    return CanonicalExecutionReport(
        exec_id=exec_id,
        client_order_id=client_id,
        track_id="Track1",
        asset_type=CanonicalAssetType.FUTURES,
        side=CanonicalOrderSide.BUY,
        executed_qty=qty,
        executed_price=price,
        fee=100.0 * qty,
        slippage=0.0,
        timestamp="2026-08-30 09:00:00",
    )


def test_scenario1_partial_4_3_3_accumulate_to_10_filled():
    """[시나리오 1] 주문수량 10: 4 → 3 → 3 = 누적 10, PARTIAL → PARTIAL → FILLED."""
    runtime = OptionProgramRuntime()
    client_id = "ORD-S1-4-3-3"
    order_uuid = _setup_order(runtime, client_id, qty=10)

    # 초기 상태
    assert runtime.oms_fsm.get_status(order_uuid) == OrderStatus.SENT
    assert runtime.get_order_executed_qty(client_id) == 0

    # 1차: 4계약 체결 -> PARTIAL (누적 4)
    runtime.consume_execution_report(_make_exec_report(client_id, "EXEC-S1-1", 4))
    assert runtime.oms_fsm.get_status(order_uuid) == OrderStatus.PARTIAL
    assert runtime.get_order_executed_qty(client_id) == 4
    assert runtime.order_router.get_executed_qty(order_uuid) == 4

    # 2차: 3계약 체결 -> PARTIAL (누적 7)
    runtime.consume_execution_report(_make_exec_report(client_id, "EXEC-S1-2", 3))
    assert runtime.oms_fsm.get_status(order_uuid) == OrderStatus.PARTIAL
    assert runtime.get_order_executed_qty(client_id) == 7
    assert runtime.order_router.get_executed_qty(order_uuid) == 7

    # 3차: 3계약 체결 -> FILLED (누적 10)
    runtime.consume_execution_report(_make_exec_report(client_id, "EXEC-S1-3", 3))
    assert runtime.oms_fsm.get_status(order_uuid) == OrderStatus.FILLED
    assert runtime.get_order_executed_qty(client_id) == 10
    assert runtime.order_router.get_executed_qty(order_uuid) == 10


def test_scenario2_single_10_immediate_filled():
    """[시나리오 2] 주문수량 10: 단일 10 = FILLED."""
    runtime = OptionProgramRuntime()
    client_id = "ORD-S2-SINGLE-10"
    order_uuid = _setup_order(runtime, client_id, qty=10)

    # 단일 10계약 전량 체결
    runtime.consume_execution_report(_make_exec_report(client_id, "EXEC-S2-1", 10))
    assert runtime.oms_fsm.get_status(order_uuid) == OrderStatus.FILLED
    assert runtime.get_order_executed_qty(client_id) == 10
    assert runtime.order_router.get_executed_qty(order_uuid) == 10


def test_scenario3_partial_2_2_6_accumulate_to_10_filled():
    """[시나리오 3] 주문수량 10: 2 → 2 → 6 = FILLED."""
    runtime = OptionProgramRuntime()
    client_id = "ORD-S3-2-2-6"
    order_uuid = _setup_order(runtime, client_id, qty=10)

    # 1차: 2계약 (누적 2, PARTIAL)
    runtime.consume_execution_report(_make_exec_report(client_id, "EXEC-S3-1", 2))
    assert runtime.oms_fsm.get_status(order_uuid) == OrderStatus.PARTIAL
    assert runtime.get_order_executed_qty(client_id) == 2

    # 2차: 2계약 (누적 4, PARTIAL)
    runtime.consume_execution_report(_make_exec_report(client_id, "EXEC-S3-2", 2))
    assert runtime.oms_fsm.get_status(order_uuid) == OrderStatus.PARTIAL
    assert runtime.get_order_executed_qty(client_id) == 4

    # 3차: 6계약 (누적 10, FILLED)
    runtime.consume_execution_report(_make_exec_report(client_id, "EXEC-S3-3", 6))
    assert runtime.oms_fsm.get_status(order_uuid) == OrderStatus.FILLED
    assert runtime.get_order_executed_qty(client_id) == 10
    assert runtime.order_router.get_executed_qty(order_uuid) == 10


def test_scenario4_partial_4_5_accumulate_to_9_remains_partial():
    """[시나리오 4] 주문수량 10: 4 → 5 = 누적 9, PARTIAL 유지."""
    runtime = OptionProgramRuntime()
    client_id = "ORD-S4-4-5"
    order_uuid = _setup_order(runtime, client_id, qty=10)

    # 1차: 4계약 (누적 4, PARTIAL)
    runtime.consume_execution_report(_make_exec_report(client_id, "EXEC-S4-1", 4))
    assert runtime.oms_fsm.get_status(order_uuid) == OrderStatus.PARTIAL
    assert runtime.get_order_executed_qty(client_id) == 4

    # 2차: 5계약 (누적 9, PARTIAL 유지)
    runtime.consume_execution_report(_make_exec_report(client_id, "EXEC-S4-2", 5))
    assert runtime.oms_fsm.get_status(order_uuid) == OrderStatus.PARTIAL
    assert runtime.get_order_executed_qty(client_id) == 9
    assert runtime.order_router.get_executed_qty(order_uuid) == 9


def test_scenario5_oversized_6_5_accumulate_to_11_triggers_rejected():
    """[시나리오 5] 주문수량 10: 6 → 5 = 누적 11, 초과 체결 REJECTED 규칙 확인."""
    runtime = OptionProgramRuntime()
    client_id = "ORD-S5-OVERSIZED"
    order_uuid = _setup_order(runtime, client_id, qty=10)

    # 1차: 6계약 (누적 6, PARTIAL)
    runtime.consume_execution_report(_make_exec_report(client_id, "EXEC-S5-1", 6))
    assert runtime.oms_fsm.get_status(order_uuid) == OrderStatus.PARTIAL
    assert runtime.get_order_executed_qty(client_id) == 6

    # 2차: 5계약 (누적 11 > 요청수량 10 -> 초과 체결 발생하여 REJECTED 전이)
    runtime.consume_execution_report(_make_exec_report(client_id, "EXEC-S5-2", 5))
    assert runtime.oms_fsm.get_status(order_uuid) == OrderStatus.REJECTED


def test_scenario6_zero_and_negative_executed_qty_triggers_rejected():
    """[시나리오 6] executed_qty 0 및 음수 체결 시 REJECTED 규칙 확인."""
    runtime = OptionProgramRuntime()

    # 1. 수량 0 체결
    client_id_zero = "ORD-S6-ZERO"
    order_uuid_zero = _setup_order(runtime, client_id_zero, qty=10)
    runtime.consume_execution_report(_make_exec_report(client_id_zero, "EXEC-S6-ZERO", 0))
    assert runtime.oms_fsm.get_status(order_uuid_zero) == OrderStatus.REJECTED

    # 2. 음수 수량 체결
    client_id_neg = "ORD-S6-NEG"
    order_uuid_neg = _setup_order(runtime, client_id_neg, qty=10)
    runtime.consume_execution_report(_make_exec_report(client_id_neg, "EXEC-S6-NEG", -2))
    assert runtime.oms_fsm.get_status(order_uuid_neg) == OrderStatus.REJECTED


def test_scenario7_broker_order_id_reverse_lookup_accumulation_regression():
    """[시나리오 7] broker_order_id 역추적을 통한 체결 귀속 및 분할 누적 체결 회귀 확인."""
    runtime = OptionProgramRuntime()
    client_id = "ORD-S7-BROKER-REVERSE"
    order_uuid = _setup_order(runtime, client_id, qty=10)

    broker_id = "BRK-REAL-S7-9999"
    ack = BrokerOrderResponse(success=True, broker_order_id=broker_id, client_order_id=client_id)
    runtime.register_broker_order_ack(ack)

    # broker_order_id만 갖는 1차 체결 (5계약)
    class ExecReportBrokerOnly:
        def __init__(self, exec_id: str, qty: int):
            self.exec_id = exec_id
            self.client_order_id = ""
            self.broker_order_id = broker_id
            self.track_id = "Track1"
            self.asset_type = CanonicalAssetType.FUTURES
            self.side = CanonicalOrderSide.BUY
            self.executed_qty = qty
            self.executed_price = 350.0
            self.fee = 500.0
            self.slippage = 0.0
            self.timestamp = "2026-08-30 09:00:00"

    runtime.consume_execution_report(ExecReportBrokerOnly("EXEC-S7-1", 5))
    assert runtime.oms_fsm.get_status(order_uuid) == OrderStatus.PARTIAL
    assert runtime.get_order_executed_qty(client_id) == 5

    # broker_order_id만 갖는 2차 체결 (5계약 -> 누적 10 FILLED)
    runtime.consume_execution_report(ExecReportBrokerOnly("EXEC-S7-2", 5))
    assert runtime.oms_fsm.get_status(order_uuid) == OrderStatus.FILLED
    assert runtime.get_order_executed_qty(client_id) == 10
    assert runtime.order_router.get_executed_qty(order_uuid) == 10


@pytest.mark.asyncio
async def test_scenario8_ack_invariance_and_separate_polling_accumulation_progression():
    """[시나리오 8] ACK 직후 executed_qty 0 / FSM SENT 유지, 체결 이벤트 소비 후에만 누적수량 및 FSM 변화 확인."""
    system = TradingSystem(config={"broker_mode": "PAPER"})
    await system.initialize()

    # 1. 1틱 실행 (주문 생성 및 Broker ACK 수신)
    await system.run_loop(max_ticks=1)

    assert system.ticks_processed == 1
    if system.orders_routed > 0:
        # [검증 A] ACK 직후에는 체결수량이 엄격히 0이며 FSM 상태는 SENT 불변
        for client_id, order_uuid in system.op_runtime._order_id_to_uuid.items():
            assert system.op_runtime.get_order_executed_qty(client_id) == 0
            assert system.op_runtime.oms_fsm.get_status(order_uuid) == OrderStatus.SENT

        # [검증 B] 별도 poll_execution_reports() 체결 수신 및 소비
        exec_reports = system.broker.poll_execution_reports()
        assert len(exec_reports) > 0, "체결 보고서가 1건 이상 존재해야 함"
        for rep in exec_reports:
            system.op_runtime.consume_execution_report(rep)

        # [검증 C] 체결 소비 후에 비로소 누적수량 반영 및 FSM FILLED 전이
        for rep in exec_reports:
            client_id = rep.client_order_id
            order_uuid = system.op_runtime._order_id_to_uuid[client_id]
            assert system.op_runtime.get_order_executed_qty(client_id) == rep.executed_qty
            assert system.op_runtime.order_router.get_executed_qty(order_uuid) == rep.executed_qty
            assert system.op_runtime.oms_fsm.get_status(order_uuid) == OrderStatus.FILLED
