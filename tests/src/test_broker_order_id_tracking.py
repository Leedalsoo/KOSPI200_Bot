"""[8단계-2] Broker Order ID 확보 및 주문 추적 매핑 권위 저장소 검증.

검증 항목:
1. 주문 접수 성공 ACK에 broker_order_id 존재
2. PAPER 경로 broker_order_id 계약
3. SHADOW 경로 broker_order_id 계약
4. REAL adapter ACK 계약이 BrokerOrderResponse와 일치
5. 실제 체결 데이터가 send_order() ACK와 혼합되지 않음 (ACK에 체결 필드 부재, 별도 poll_execution_reports 분리 수신)
6. client/internal ID ↔ broker_order_id 매핑 저장 및 조회 (OrderRouter & OptionProgramRuntime)
7. 실제 TradingSystem.run_loop() 실행 시 broker_order_id 매핑 자동 등록 및 단대단 추적 일치성
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
    CanonicalMarketTick,
)
from shared.core.contracts import OrderStatus, RiskApprovalToken
from option_program.broker.broker_interface import (
    BrokerOrderResponse,
    PaperBrokerAdapter,
    ShadowBrokerAdapter,
)
from option_program.broker.real_broker_adapter import RealBrokerAdapter, RealBrokerConfig
from option_program.orders.order_router import OrderRouter
from option_program.orders.oms_fsm import OmsFsm
from option_program.runtime.program_runtime import OptionProgramRuntime
from main import TradingSystem


def _make_dummy_command(client_order_id: str, track_id: str = "Track1") -> CanonicalOrderCommand:
    return CanonicalOrderCommand(
        client_order_id=client_order_id,
        track_id=track_id,
        asset_type=CanonicalAssetType.FUTURES,
        side=CanonicalOrderSide.BUY,
        qty=1,
        price=350.0,
        symbol="KOSPI200",
    )


def test_paper_and_shadow_broker_order_id_contract():
    """[검증 1, 2, 3] PAPER 및 SHADOW 경로에서 send_order()가 유효한 broker_order_id가 포함된 BrokerOrderResponse를 반환함을 검증."""
    cmd_paper = _make_dummy_command("ORD-TEST-PAPER-01")
    cmd_shadow = _make_dummy_command("ORD-TEST-SHADOW-01")

    # 1. PAPER 브로커 검증
    paper_broker = PaperBrokerAdapter()
    ack_paper = paper_broker.send_order(cmd_paper)

    assert isinstance(ack_paper, BrokerOrderResponse), "PAPER send_order must return BrokerOrderResponse"
    assert ack_paper.success is True
    assert ack_paper.client_order_id == "ORD-TEST-PAPER-01"
    assert ack_paper.broker_order_id.startswith("BRK-PAPER-"), f"Unexpected PAPER broker_order_id: {ack_paper.broker_order_id}"
    assert ack_paper.status == "ACCEPTED"

    # 2. SHADOW 브로커 검증
    shadow_broker = ShadowBrokerAdapter()
    ack_shadow = shadow_broker.send_order(cmd_shadow)

    assert isinstance(ack_shadow, BrokerOrderResponse), "SHADOW send_order must return BrokerOrderResponse"
    assert ack_shadow.success is True
    assert ack_shadow.client_order_id == "ORD-TEST-SHADOW-01"
    assert ack_shadow.broker_order_id.startswith("BRK-SHADOW-"), f"Unexpected SHADOW broker_order_id: {ack_shadow.broker_order_id}"
    assert ack_shadow.status == "ACCEPTED"


def test_real_broker_adapter_ack_contract_and_execution_separation():
    """[검증 4, 5] REAL 어댑터의 send_order()가 BrokerOrderResponse ACK를 반환하고 실제 체결은 poll_execution_reports()로 분리됨을 검증."""
    config = RealBrokerConfig(is_simulation=True)
    real_broker = RealBrokerAdapter(config=config)
    connected = real_broker.connect()
    assert connected is True
    assert real_broker.is_connected() is True

    cmd_real = _make_dummy_command("ORD-TEST-REAL-01")
    ack_real = real_broker.send_order(cmd_real)

    # 1. BrokerOrderResponse ACK 계약 검증
    assert isinstance(ack_real, BrokerOrderResponse), "REAL send_order must return BrokerOrderResponse"
    assert ack_real.success is True
    assert ack_real.client_order_id == "ORD-TEST-REAL-01"
    assert ack_real.broker_order_id.startswith("BRK-REAL-ORD-"), f"Unexpected REAL broker_order_id: {ack_real.broker_order_id}"
    assert ack_real.status == "ACCEPTED"

    # 2. ACK 객체에 체결 필드 부재 확인 (체결 데이터 혼합 방지)
    assert not hasattr(ack_real, "executed_qty")
    assert not hasattr(ack_real, "executed_price")
    assert not hasattr(ack_real, "exec_id")

    # 3. 별도 poll_execution_reports()를 통한 실제 CanonicalExecutionReport 수신 확인
    exec_reports = real_broker.poll_execution_reports()
    assert len(exec_reports) == 1
    rep = exec_reports[0]
    assert isinstance(rep, CanonicalExecutionReport)
    assert rep.client_order_id == "ORD-TEST-REAL-01"
    assert rep.executed_qty == 1
    assert rep.exec_id.startswith("EXEC-REAL-ORD-")

    # 추가 폴링 시 큐가 비워져 0건 반환됨을 확인
    empty_reports = real_broker.poll_execution_reports()
    assert len(empty_reports) == 0


def test_order_router_broker_order_id_mapping_and_lookup():
    """[검증 6] OrderRouter 주문 추적 권위 저장소에서 client_order_id/order_uuid ↔ broker_order_id 양방향 매핑 및 조회 검증."""
    fsm = OmsFsm()
    router = OrderRouter(fsm=fsm)

    order_uuid = uuid.uuid4()
    client_id = "ORD-TEST-ROUTE-01"
    cmd = _make_dummy_command(client_id)
    token = RiskApprovalToken(
        order_id=order_uuid,
        timestamp_ns=1000000,
        signature=f"SIG-RISK-APPROVED-Track1-{client_id}",
    )

    # 1. OrderRouter에 주문 등록
    registered_id = router.register_and_route(command=cmd, token=token)
    assert registered_id == order_uuid
    assert fsm.get_status(order_uuid) == OrderStatus.SENT

    # 등록 직후 broker_order_id는 None
    assert router.get_broker_order_id(order_uuid) is None
    assert router.get_broker_order_id(client_id) is None

    # 2. broker_order_id 등록
    broker_id = "BRK-PAPER-98765432"
    router.register_broker_order_id(order_uuid, broker_id)

    # 3. order_uuid 및 client_order_id 양방향 조회 검증
    assert router.get_broker_order_id(order_uuid) == broker_id
    assert router.get_broker_order_id(client_id) == broker_id
    assert router.get_client_order_id_by_broker_id(broker_id) == client_id

    # 4. 문자열 client_id로 직접 등록하는 경로도 검증
    client_id_2 = "ORD-TEST-ROUTE-02"
    cmd_2 = _make_dummy_command(client_id_2)
    order_uuid_2 = uuid.uuid4()
    token_2 = RiskApprovalToken(
        order_id=order_uuid_2,
        timestamp_ns=2000000,
        signature=f"SIG-RISK-APPROVED-Track1-{client_id_2}",
    )
    router.register_and_route(command=cmd_2, token=token_2)
    broker_id_2 = "BRK-SHADOW-12345678"
    router.register_broker_order_id(client_id_2, broker_id_2)

    assert router.get_broker_order_id(client_id_2) == broker_id_2
    assert router.get_broker_order_id(order_uuid_2) == broker_id_2
    assert router.get_client_order_id_by_broker_id(broker_id_2) == client_id_2


def test_option_program_runtime_broker_order_ack_integration():
    """[검증 6-2] OptionProgramRuntime에서 Broker ACK 수신 시 OrderRouter에 자동 매핑 등록 및 조회 기능 검증."""
    runtime = OptionProgramRuntime()

    client_id = "ORD-RUNTIME-ACK-01"
    order_uuid = uuid.uuid4()
    runtime._order_id_to_uuid[client_id] = order_uuid

    ack = BrokerOrderResponse(
        success=True,
        broker_order_id="BRK-PAPER-A1B2C3D4",
        client_order_id=client_id,
        status="ACCEPTED",
    )

    runtime.register_broker_order_ack(ack)

    # OptionProgramRuntime 및 OrderRouter에서 동일하게 broker_order_id 조회 가능
    assert runtime.get_broker_order_id(client_id) == "BRK-PAPER-A1B2C3D4"
    assert runtime.order_router.get_broker_order_id(client_id) == "BRK-PAPER-A1B2C3D4"
    assert runtime.order_router.get_broker_order_id(order_uuid) == "BRK-PAPER-A1B2C3D4"


@pytest.mark.asyncio
async def test_actual_tradingsystem_run_loop_broker_order_id_tracking_functional_assertion():
    """[검증 7] 실제 TradingSystem.run_loop() 실행 시 발주된 주문에 대해 broker_order_id가 정상 발급 및 매핑 등록됨을 단대단 실측."""
    system = TradingSystem(config={"broker_mode": "PAPER"})
    await system.initialize()

    # 1 틱 실행하여 주문 접수 및 ACK 확보
    await system.run_loop(max_ticks=1)

    assert system.ticks_processed == 1
    if system.orders_routed > 0:
        # 발주된 모든 주문에 대해 broker_order_id가 OrderRouter 및 OptionProgramRuntime에 저장되어 있어야 함
        for client_id, order_uuid in system.op_runtime._order_id_to_uuid.items():
            broker_id = system.op_runtime.get_broker_order_id(client_id)
            assert broker_id is not None, f"Order {client_id} must have a registered broker_order_id"
            assert broker_id.startswith("BRK-PAPER-"), f"Unexpected broker_order_id format: {broker_id}"
            assert system.op_runtime.order_router.get_broker_order_id(order_uuid) == broker_id
            assert system.op_runtime.order_router.get_client_order_id_by_broker_id(broker_id) == client_id
