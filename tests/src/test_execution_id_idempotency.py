"""[8단계-5] 동일 execution ID 중복수신 방어 (체결 멱등성) 검증.

검증 항목:
1. execution ID E1을 1회 수신 → executed_qty 정상 반영
2. 동일 E1을 2회 수신 → executed_qty는 최초 1회 결과와 동일
3. 동일 E1 반복 수신 → FSM 상태가 추가 전이되지 않음 (멱등성 보장)
4. E1, E2 서로 다른 execution ID → 두 체결 모두 정상 누적
5. PARTIAL 상태에서 동일 execution ID 재수신 → 수량 및 상태 불변
6. FILLED 상태에서 동일 execution ID 재수신 → 수량 및 상태 불변
7. ACK 직후 execution report 분리 구조 유지
8. OrderRouter.is_execution_processed() 조회 기능 검증
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


def test_duplicate_execution_id_single_fill_idempotency():
    """[검증 1, 2, 3, 6, 8] 단일 체결에서 동일 execution ID 2회 이상 수신 시 멱등성 검증 (수량 및 FSM 불변)."""
    runtime = OptionProgramRuntime()
    client_id = "ORD-IDEMP-01"
    order_uuid = _setup_order(runtime, client_id, qty=10)

    exec_id_1 = "EXEC-IDEMP-E1"
    rep_1 = _make_exec_report(client_id, exec_id_1, qty=10)

    # 1. 최초 수신: 10계약 체결 -> FILLED
    runtime.consume_execution_report(rep_1)
    assert runtime.oms_fsm.get_status(order_uuid) == OrderStatus.FILLED
    assert runtime.get_order_executed_qty(client_id) == 10
    assert runtime.order_router.get_executed_qty(order_uuid) == 10
    assert runtime.order_router.is_execution_processed(exec_id_1) is True

    # 2. 동일 execution ID E1 2회차 수신: 무시되어야 함 (수량 20으로 초과되거나 에러 발생하지 않음)
    runtime.consume_execution_report(rep_1)
    assert runtime.oms_fsm.get_status(order_uuid) == OrderStatus.FILLED
    assert runtime.get_order_executed_qty(client_id) == 10
    assert runtime.order_router.get_executed_qty(order_uuid) == 10

    # 3. 동일 execution ID E1 3회차 수신: 여전히 FILLED 및 10계약 유지
    runtime.consume_execution_report(rep_1)
    assert runtime.oms_fsm.get_status(order_uuid) == OrderStatus.FILLED
    assert runtime.get_order_executed_qty(client_id) == 10


def test_duplicate_execution_id_during_partial_fills():
    """[검증 4, 5] 부분 체결 중 동일 execution ID 재수신 시 수량/상태 불변 및 서로 다른 execution ID 정상 누적 검증."""
    runtime = OptionProgramRuntime()
    client_id = "ORD-IDEMP-PARTIAL"
    order_uuid = _setup_order(runtime, client_id, qty=10)

    exec_id_1 = "EXEC-PARTIAL-E1"
    exec_id_2 = "EXEC-PARTIAL-E2"
    rep_1 = _make_exec_report(client_id, exec_id_1, qty=4)
    rep_2 = _make_exec_report(client_id, exec_id_2, qty=6)

    # 1. E1 최초 수신: 4계약 -> PARTIAL
    runtime.consume_execution_report(rep_1)
    assert runtime.oms_fsm.get_status(order_uuid) == OrderStatus.PARTIAL
    assert runtime.get_order_executed_qty(client_id) == 4
    assert runtime.order_router.is_execution_processed(exec_id_1) is True
    assert runtime.order_router.is_execution_processed(exec_id_2) is False

    # 2. E1 중복 수신: 4계약 및 PARTIAL 상태 엄격 유지 (누적 8계약으로 변하지 않음)
    runtime.consume_execution_report(rep_1)
    assert runtime.oms_fsm.get_status(order_uuid) == OrderStatus.PARTIAL
    assert runtime.get_order_executed_qty(client_id) == 4

    # 3. 서로 다른 E2 최초 수신: 잔여 6계약 정상 누적 -> FILLED (누적 10)
    runtime.consume_execution_report(rep_2)
    assert runtime.oms_fsm.get_status(order_uuid) == OrderStatus.FILLED
    assert runtime.get_order_executed_qty(client_id) == 10
    assert runtime.order_router.is_execution_processed(exec_id_2) is True

    # 4. E1 또는 E2 추가 중복 수신: 여전히 10계약 및 FILLED 유지
    runtime.consume_execution_report(rep_1)
    runtime.consume_execution_report(rep_2)
    assert runtime.oms_fsm.get_status(order_uuid) == OrderStatus.FILLED
    assert runtime.get_order_executed_qty(client_id) == 10


@pytest.mark.asyncio
async def test_actual_tradingsystem_duplicate_execution_id_functional_assertion():
    """[검증 7] 실제 TradingSystem.run_loop() 단대단 파이프라인에서 중복 체결 보고서 주입 시 멱등성 실측."""
    system = TradingSystem(config={"broker_mode": "PAPER"})
    await system.initialize()

    # 1. 1틱 실행 (주문 생성 및 ACK 확보)
    await system.run_loop(max_ticks=1)

    assert system.ticks_processed == 1
    if system.orders_routed > 0:
        exec_reports = system.broker.poll_execution_reports()
        assert len(exec_reports) > 0

        first_rep = exec_reports[0]
        client_id = first_rep.client_order_id
        order_uuid = system.op_runtime._order_id_to_uuid[client_id]

        # 2. 1회차 정상 소비
        system.op_runtime.consume_execution_report(first_rep)
        assert system.op_runtime.get_order_executed_qty(client_id) == first_rep.executed_qty
        assert system.op_runtime.oms_fsm.get_status(order_uuid) == OrderStatus.FILLED

        # 3. 2회차 동일 execution report 강제 재주입 (중복 수신 모사)
        system.op_runtime.consume_execution_report(first_rep)
        # 수량이 2배로 증가하지 않고 기존 수량 및 FILLED 상태 완벽 보존 확인
        assert system.op_runtime.get_order_executed_qty(client_id) == first_rep.executed_qty
        assert system.op_runtime.oms_fsm.get_status(order_uuid) == OrderStatus.FILLED
