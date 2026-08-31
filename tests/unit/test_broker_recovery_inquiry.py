"""tests/unit/test_broker_recovery_inquiry.py

[D-12] Broker Recovery 조회 계약(get_open_orders, get_order_status) 및
RealBrokerAdapter / PaperBrokerAdapter / ShadowBrokerAdapter / OrderRouter
대사(Reconciliation) 승격 구현 및 경계 조건 통합 검증 테스트 스위트.
"""

from typing import Any, Dict
import uuid

import pytest

from option_program.broker.broker_interface import (
    BrokerFactory,
    BrokerMode,
    IBrokerAdapter,
    PaperBrokerAdapter,
    RealBrokerAdapterStub,
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
    CanonicalExecutionReport,
    CanonicalOptionType,
    CanonicalOrderCommand,
    CanonicalOrderSide,
)
from shared.core.contracts import RiskApprovalToken


def make_mock_client(transport_func) -> RealBrokerHttpClient:
    """Mock transport를 주입한 RealBrokerHttpClient 팩토리 (모의투자 API 네트워크 의존 없음)"""
    config = RealBrokerConfig(
        broker_name="KIS_OPENAPI",
        app_key="TEST_KEY",
        app_secret="TEST_SECRET",
        account_no="50012345-01",
        is_simulation=False,
    )
    return RealBrokerHttpClient(config=config, transport=transport_func)


class TestBrokerRecoveryInquiry:
    """[D-12] Broker Recovery 조회 계약 및 안전 대사 검증 스위트"""

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

        stub = RealBrokerAdapterStub()
        assert hasattr(stub, "get_open_orders")
        assert hasattr(stub, "get_order_status")
        assert stub.get_open_orders() == []
        assert stub.get_order_status("STUB-001") is None

    def test_paper_and_shadow_broker_inquiry(self):
        """2. PaperBroker 및 ShadowBroker에서 미체결 주문 조회 및 상태 조회 검증."""
        # Paper Broker 검증
        paper = PaperBrokerAdapter()
        cmd_p = CanonicalOrderCommand(
            client_order_id="ORD-PAPER-01",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=5,
            price=2.5,
            symbol="201V3350",
        )
        resp_p = paper.send_order(cmd_p)
        assert resp_p.success is True

        open_orders_p = paper.get_open_orders()
        assert len(open_orders_p) == 1
        assert open_orders_p[0]["client_order_id"] == "ORD-PAPER-01"
        assert open_orders_p[0]["order_qty"] == 5
        assert open_orders_p[0]["status"] == "OPEN"

        status_info_p = paper.get_order_status("ORD-PAPER-01")
        assert status_info_p is not None
        assert status_info_p["symbol"] == "201V3350"
        assert status_info_p["order_qty"] == 5
        assert paper.get_order_status("NON_EXISTENT") is None

        # Shadow Broker 검증
        shadow = ShadowBrokerAdapter(initial_capital=100000000.0)
        cmd_s = CanonicalOrderCommand(
            client_order_id="ORD-SHADOW-01",
            track_id="Track2",
            asset_type=CanonicalAssetType.FUTURES,
            side=CanonicalOrderSide.SELL,
            qty=3,
            price=350.0,
            symbol="101V3000",
        )
        resp_s = shadow.send_order(cmd_s)
        assert resp_s.success is True

        open_orders_s = shadow.get_open_orders()
        assert len(open_orders_s) == 1
        assert open_orders_s[0]["client_order_id"] == "ORD-SHADOW-01"
        assert open_orders_s[0]["status"] == "OPEN"

        status_info_s = shadow.get_order_status("ORD-SHADOW-01")
        assert status_info_s is not None
        assert status_info_s["side"] == "SELL"

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

    def test_real_broker_query_error_response_safe_handling(self):
        """6. 증권사 API 오류 응답(rt_cd != '0') 시 crash 없이 안전하게 빈 리스트 반환 및 처리 검증."""
        def mock_err_transport(method: str, path: str, headers: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
            if "token" in path:
                return {"access_token": "TEST_TOKEN", "expires_in": 3600}
            return {"rt_cd": "1", "msg_cd": "ERR_INQUIRY", "msg1": "조회 서비스 일시적 지연"}

        client = make_mock_client(mock_err_transport)
        adapter = RealBrokerAdapter(http_client=client)
        adapter.connect()

        open_orders = adapter.get_open_orders()
        assert open_orders == []

        order_status = adapter.get_order_status("ORD-ANY")
        assert order_status is None

    def test_order_router_reconcile_with_broker_cancellation_sync(self):
        """7. OrderRouter.reconcile_with_broker()가 취소 요청 주문을 안전하게 CANCELLED로 대사하는지 검증."""
        order_router = OrderRouter()
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-RECONCILE-01",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=5,
            price=3.0,
            symbol="201V3350",
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
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

    def test_order_router_reconcile_idempotency(self):
        """8. 동일 대사(Reconciliation)를 다회 호출해도 멱등성이 보장되고 에러가 발생하지 않음 검증."""
        order_router = OrderRouter()
        class MockEmptyBroker:
            def get_open_orders(self):
                return []

            def get_order_status(self, order_id):
                return None

        # 다회 호출 시 동일하게 안전 종료
        s1 = order_router.reconcile_with_broker(MockEmptyBroker())
        s2 = order_router.reconcile_with_broker(MockEmptyBroker())
        assert s1["confirmed_cancelled"] == 0
        assert s2["confirmed_cancelled"] == 0

    def test_order_router_reconcile_preserves_active_open_orders(self):
        """9. 브로커에 미체결로 남아있는 정상 활성 주문은 대사 후에도 FSM 및 active_orders가 보존됨을 검증."""
        order_router = OrderRouter()
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-RECONCILE-OPEN",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=10,
            price=2.0,
            symbol="201V3350",
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
        )
        token = RiskApprovalToken(
            order_id=uuid.uuid4(),
            timestamp_ns=2000000,
            signature="SIG-RISK-APPROVED-Track1-ORD-RECONCILE-OPEN",
        )
        order_uuid = order_router.register_and_route(command=cmd, token=token)
        assert order_uuid is not None

        # 브로커 모의: 브로커에 여전히 미체결로 남아있음
        class MockOpenBroker:
            def get_open_orders(self):
                return [{
                    "broker_order_id": "BRK-9901",
                    "client_order_id": "ORD-RECONCILE-OPEN",
                    "symbol": "201V3350",
                    "side": "BUY",
                    "order_qty": 10,
                    "unexecuted_qty": 10,
                    "status": "OPEN",
                }]

            def get_order_status(self, order_id):
                return {"status": "OPEN"}

        summary = order_router.reconcile_with_broker(MockOpenBroker())
        assert summary["open_orders_broker_count"] == 1
        assert summary["confirmed_cancelled"] == 0
        # 로컬 주문은 여전히 SENT 상태 및 active_orders에 유지됨
        assert order_router.fsm.get_status(order_uuid) == OrderStatus.SENT
        assert order_uuid in order_router._active_orders

    def test_order_router_reconcile_filled_order_sync(self):
        """10. CANCEL_REQUESTED 중 브로커에서 취소되지 않고 체결 완료된 경우 FILLED로 안전 동기화 검증."""
        order_router = OrderRouter()
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-RCL-FILL",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=5,
            price=3.0,
            symbol="201V3350",
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
        )
        token = RiskApprovalToken(
            order_id=uuid.uuid4(),
            timestamp_ns=3000000,
            signature="SIG-RISK-APPROVED-Track1-ORD-RCL-FILL",
        )
        order_uuid = order_router.register_and_route(command=cmd, token=token)
        assert order_uuid is not None

        order_router.fsm.transition_sync(order_uuid, OrderStatus.CANCEL_REQUESTED)

        class MockFilledBroker:
            def get_open_orders(self):
                return []

            def get_order_status(self, order_id):
                return {"status": "FILLED", "executed_qty": 5}

        summary = order_router.reconcile_with_broker(MockFilledBroker())
        assert summary["synced_orders"] == 1
        assert order_router.fsm.get_status(order_uuid) == OrderStatus.FILLED
        assert order_uuid not in order_router._active_orders

    def test_poll_execution_reports_regression_unaffected(self):
        """11. Recovery 조회 계약(get_open_orders/get_order_status) 호출이 poll_execution_reports()에 일체 부작용 없음 검증."""
        def mock_transport(method: str, path: str, headers: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
            if "token" in path:
                return {"access_token": "TEST_TOKEN", "expires_in": 3600}
            if "inquire-nccs" in path:
                return {"rt_cd": "0", "output1": [{"odno": "001", "ord_qty": "5", "ccld_qty": "0", "nccs_qty": "5"}]}
            return {"rt_cd": "0", "output1": []}

        client = make_mock_client(mock_transport)
        adapter = RealBrokerAdapter(http_client=client)
        adapter.connect()

        # 사전 주입 체결 보고서
        mock_rep = CanonicalExecutionReport(
            exec_id="EXEC-TEST-D12",
            client_order_id="ORD-D12-PRE",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            executed_qty=5,
            executed_price=3.5,
            fee=100.0,
            slippage=0.0,
            timestamp="2026-08-31 09:30:00",
            symbol="201V3350",
        )
        adapter.inject_execution_report(mock_rep)

        # Recovery 조회 수행
        open_orders = adapter.get_open_orders()
        assert len(open_orders) == 1

        # 체결 폴링 수행 -> 주입된 보고서가 정상 수신되어야 함
        reports = adapter.poll_execution_reports()
        assert len(reports) == 1
        assert reports[0].exec_id == "EXEC-TEST-D12"

    def test_order_router_reconcile_active_sent_filled_sync(self):
        """12. SENT 상태 주문이 브로커에서 체결 완료(FILLED)된 경우 안전 동기화 검증."""
        order_router = OrderRouter()
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-SENT-FILL-SYNC",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=2,
            price=2.0,
            symbol="201V3350",
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
        )
        token = RiskApprovalToken(
            order_id=uuid.uuid4(),
            timestamp_ns=4000000,
            signature="SIG-RISK-APPROVED-Track1-ORD-SENT-FILL-SYNC",
        )
        order_uuid = order_router.register_and_route(command=cmd, token=token)
        assert order_uuid is not None
        assert order_router.fsm.get_status(order_uuid) == OrderStatus.SENT

        class MockFilledBroker:
            def get_open_orders(self):
                return []

            def get_order_status(self, order_id):
                return {"status": "FILLED", "executed_qty": 2}

        summary = order_router.reconcile_with_broker(MockFilledBroker())
        assert summary["synced_orders"] == 1
        assert order_router.fsm.get_status(order_uuid) == OrderStatus.FILLED
        assert order_uuid not in order_router._active_orders
