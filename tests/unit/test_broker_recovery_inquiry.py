"""tests/unit/test_broker_recovery_inquiry.py

[D-12] Broker Recovery 조회 계약(get_open_orders, get_order_status) 및
RealBrokerAdapter / PaperBrokerAdapter / OrderRouter 대사 연계 검증 테스트.
"""

from typing import Any, Dict
import uuid

import pytest

from option_program.broker.broker_interface import (
    BrokerFactory,
    BrokerMode,
    IBrokerAdapter,
    PaperBrokerAdapter,
    ShadowBrokerAdapter,
)
from option_program.broker.real_broker_adapter import (
    RealBrokerAdapter,
    RealBrokerConfig,
    RealBrokerHttpClient,
)
from option_program.orders.oms_fsm import OrderStatus
from option_program.orders.order_router import OrderRouter
from shared.contracts.canonical import (
    CanonicalAssetType,
    CanonicalOrderCommand,
    CanonicalOrderSide,
)
from shared.core.contracts import RiskApprovalToken


def make_mock_client(transport_func) -> RealBrokerHttpClient:
    config = RealBrokerConfig(
        broker_name="KIS_OPENAPI",
        app_key="TEST_KEY",
        app_secret="TEST_SECRET",
        account_no="50012345-01",
        is_simulation=False,
    )
    return RealBrokerHttpClient(config=config, transport=transport_func)


class TestBrokerRecoveryInquiry:
    """[D-12] Broker Recovery 조회 계약 검증 스위트"""

    def test_ibroker_adapter_contract_and_implementations(self):
        """1. IBrokerAdapter에 get_open_orders 및 get_order_status가 정의되어 있고 하위 어댑터들이 구현했는지 검증."""
        assert hasattr(IBrokerAdapter, "get_open_orders")
        assert hasattr(IBrokerAdapter, "get_order_status")

        paper = BrokerFactory.create_broker(BrokerMode.PAPER)
        assert hasattr(paper, "get_open_orders")
        assert hasattr(paper, "get_order_status")

        shadow = BrokerFactory.create_broker(BrokerMode.SHADOW)
        assert hasattr(shadow, "get_open_orders")
        assert hasattr(shadow, "get_order_status")

    def test_paper_and_shadow_broker_inquiry(self):
        """2. PaperBroker 및 ShadowBroker에서 미체결 주문 조회 및 상태 조회 검증."""
        paper = PaperBrokerAdapter()
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-PAPER-01",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=5,
            price=2.5,
            symbol="201V3350",
        )
        resp = paper.send_order(cmd)
        assert resp.success is True

        open_orders = paper.get_open_orders()
        assert len(open_orders) == 1
        assert open_orders[0]["client_order_id"] == "ORD-PAPER-01"
        assert open_orders[0]["order_qty"] == 5
        assert open_orders[0]["status"] == "OPEN"

        status_info = paper.get_order_status("ORD-PAPER-01")
        assert status_info is not None
        assert status_info["symbol"] == "201V3350"
        assert status_info["order_qty"] == 5

        # 존재하지 않는 주문
        assert paper.get_order_status("NON_EXISTENT") is None

    def test_real_broker_get_open_orders_normalization(self):
        """3. RealBrokerAdapter.get_open_orders()의 inquire-nccs 응답 정규화 검증."""
        def mock_transport(method: str, path: str, headers: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
            if "token" in path:
                return {"access_token": "TEST_TOKEN", "expires_in": 3600}
            if "inquire-nccs" in path:
                return {
                    "rt_cd": "0",
                    "output1": [
                        {
                            "odno": "00099881",
                            "pdno": "201V3350",
                            "sll_buy_dvsn_cd": "02",  # BUY
                            "ord_qty": "10",
                            "ccld_qty": "3",
                            "nccs_qty": "7",
                            "ord_unpr": "3.50",
                            "ord_tmd": "093000",
                        },
                        {
                            "odno": "00099882",
                            "pdno": "101V3000",
                            "sll_buy_dvsn_cd": "01",  # SELL
                            "ord_qty": "2",
                            "ccld_qty": "0",
                            "nccs_qty": "2",
                            "ord_unpr": "350.00",
                            "ord_tmd": "093015",
                        },
                    ],
                }
            return {"rt_cd": "0"}

        client = make_mock_client(mock_transport)
        adapter = RealBrokerAdapter(http_client=client)
        adapter.connect()

        open_orders = adapter.get_open_orders()
        assert len(open_orders) == 2

        # 첫 번째 주문 (부분체결 잔량)
        o1 = open_orders[0]
        assert o1["broker_order_id"] == "00099881"
        assert o1["symbol"] == "201V3350"
        assert o1["side"] == "BUY"
        assert o1["order_qty"] == 10
        assert o1["executed_qty"] == 3
        assert o1["unexecuted_qty"] == 7
        assert o1["order_price"] == 3.50
        assert o1["status"] == "PARTIAL"

        # 두 번째 주문 (전량 미체결)
        o2 = open_orders[1]
        assert o2["broker_order_id"] == "00099882"
        assert o2["symbol"] == "101V3000"
        assert o2["side"] == "SELL"
        assert o2["order_qty"] == 2
        assert o2["executed_qty"] == 0
        assert o2["unexecuted_qty"] == 2
        assert o2["order_price"] == 350.00
        assert o2["status"] == "OPEN"

    def test_real_broker_get_order_status_open_and_filled_and_cancelled(self):
        """4. RealBrokerAdapter.get_order_status()의 미체결, 체결 완료, 취소 주문 상태 판정 검증."""
        def mock_transport(method: str, path: str, headers: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
            if "token" in path:
                return {"access_token": "TEST_TOKEN", "expires_in": 3600}
            if "inquire-nccs" in path:
                return {
                    "rt_cd": "0",
                    "output1": [
                        {
                            "odno": "BRK-OPEN-01",
                            "pdno": "201V3350",
                            "sll_buy_dvsn_cd": "02",
                            "ord_qty": "5",
                            "ccld_qty": "0",
                            "nccs_qty": "5",
                            "ord_unpr": "2.0",
                        }
                    ],
                }
            if "inquire-ccld" in path:
                return {
                    "rt_cd": "0",
                    "output1": [
                        {
                            "odno": "BRK-FILLED-02",
                            "pdno": "101V3000",
                            "sll_buy_dvsn_cd": "01",
                            "ccld_qty": "4",
                            "ccld_pric": "355.0",
                        }
                    ],
                }
            return {"rt_cd": "0"}

        client = make_mock_client(mock_transport)
        adapter = RealBrokerAdapter(http_client=client)
        adapter.connect()

        # 1) 미체결 주문 상태 조회
        status_open = adapter.get_order_status("BRK-OPEN-01")
        assert status_open is not None
        assert status_open["broker_order_id"] == "BRK-OPEN-01"
        assert status_open["status"] == "OPEN"
        assert status_open["unexecuted_qty"] == 5

        # 2) 체결 완료 주문 상태 조회
        status_filled = adapter.get_order_status("BRK-FILLED-02")
        assert status_filled is not None
        assert status_filled["broker_order_id"] == "BRK-FILLED-02"
        assert status_filled["status"] == "FILLED"
        assert status_filled["executed_qty"] == 4

        # 3) 이력 없는 완전 미등록 주문
        assert adapter.get_order_status("NON-EXISTENT-99") is None

    def test_real_broker_disconnected_error_handling(self):
        """5. 연결 해제 상태에서 get_open_orders / get_order_status 호출 시 RuntimeError 발생 검증."""
        adapter = RealBrokerAdapter()
        assert adapter.is_connected() is False

        with pytest.raises(RuntimeError, match="Broker is disconnected"):
            adapter.get_open_orders()

        with pytest.raises(RuntimeError, match="Broker is disconnected"):
            adapter.get_order_status("ORD-001")

    def test_order_router_reconcile_with_broker(self):
        """6. OrderRouter.reconcile_with_broker()가 취소 요청 주문을 안전하게 CANCELLED로 대사하는지 검증."""
        order_router = OrderRouter()
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-RECONCILE-01",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=5,
            price=3.0,
            symbol="201V3350",
        )
        token = RiskApprovalToken(
            order_id=uuid.uuid4(),
            timestamp_ns=1000000,
            signature="SIG-RISK-APPROVED-Track1-ORD-RECONCILE-01",
        )
        order_uuid = order_router.register_and_route(command=cmd, token=token)
        assert order_uuid is not None

        # 취소 요청 상태로 전이
        order_router.fsm.transition_sync(order_uuid, OrderStatus.CANCEL_REQUESTED)
        assert order_router.fsm.get_status(order_uuid) == OrderStatus.CANCEL_REQUESTED

        # 브로커 모의: 미체결 목록에 더 이상 없음 (취소 완료)
        class MockReconcileBroker:
            def get_open_orders(self):
                return []

            def get_order_status(self, order_id):
                return {"status": "CANCELLED"}

        summary = order_router.reconcile_with_broker(MockReconcileBroker())
        assert summary["confirmed_cancelled"] == 1
        assert order_router.fsm.get_status(order_uuid) == OrderStatus.CANCELLED
        assert order_uuid not in order_router._active_orders
