"""Unit and Integration tests for D-11 Real Broker Execution Receiver Layer.

Verifies:
1. RealBrokerAdapter.poll_execution_reports() receives broker execution records from inquire-ccld API
2. Execution records are normalized to CanonicalExecutionReport with proper fields (symbol, asset_type, side, price, qty)
3. Lifecycle: start/stop listener tied to connect() and disconnect()
4. Disconnected broker returns empty execution reports list
5. Idempotency: duplicate execution records are filtered and not returned multiple times
6. inject_execution_report() works for WebSocket/external injection queue
7. End-to-end integration: poll_execution_reports() -> OptionProgramRuntime.consume_execution_report() -> OrderRouter FSM update
8. Safe error handling: API exceptions do not crash poll_execution_reports()
"""
import uuid
import pytest
from typing import Dict, Any

from shared.contracts.canonical import (
    CanonicalExecutionReport,
    CanonicalAssetType,
    CanonicalOrderSide,
    CanonicalOrderCommand,
)
from shared.core.contracts import OrderStatus, RiskApprovalToken
from option_program.broker.real_broker_adapter import RealBrokerAdapter, RealBrokerConfig, RealBrokerHttpClient
from option_program.runtime.program_runtime import OptionProgramRuntime


def make_mock_client(transport_func):
    config = RealBrokerConfig(app_key="TEST_KEY", app_secret="TEST_SECRET", is_simulation=False)
    return RealBrokerHttpClient(config=config, transport=transport_func)


class TestRealBrokerExecutionReceiver:
    """D-11 실제 증권사 체결 수신 계층 검증."""

    def test_poll_execution_reports_normalization_options_and_futures(self):
        """1. inquire-ccld 응답의 선물 및 옵션 체결 데이터 정규화 검증."""
        def mock_transport(method: str, path: str, headers: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
            if "token" in path:
                return {"access_token": "TEST_TOKEN", "expires_in": 3600}
            if "inquire-ccld" in path:
                return {
                    "rt_cd": "0",
                    "output1": [
                        {
                            "odno": "00012345",
                            "ord_tmd": "091530",
                            "pdno": "201V3350",
                            "sll_buy_dvsn_cd": "02",  # BUY
                            "ccld_qty": "5",
                            "ccld_pric": "3.85",
                            "fee": "120.0",
                        },
                        {
                            "odno": "00012346",
                            "ord_tmd": "091540",
                            "pdno": "101V3000",
                            "sll_buy_dvsn_cd": "01",  # SELL
                            "ccld_qty": "2",
                            "ccld_pric": "350.50",
                            "fee": "500.0",
                        },
                    ],
                }
            return {"rt_cd": "0"}

        client = make_mock_client(mock_transport)
        adapter = RealBrokerAdapter(http_client=client)
        assert adapter.connect() is True

        reports = adapter.poll_execution_reports()
        assert len(reports) == 2

        # 1번째 체결 (콜옵션 매수)
        r1 = reports[0]
        assert isinstance(r1, CanonicalExecutionReport)
        assert r1.client_order_id == "00012345"
        assert r1.symbol == "201V3350"
        assert r1.asset_type == CanonicalAssetType.OPTION
        assert r1.side == CanonicalOrderSide.BUY
        assert r1.executed_qty == 5
        assert r1.executed_price == 3.85
        assert r1.fee == 120.0

        # 2번째 체결 (지수선물 매도)
        r2 = reports[1]
        assert isinstance(r2, CanonicalExecutionReport)
        assert r2.client_order_id == "00012346"
        assert r2.symbol == "101V3000"
        assert r2.asset_type == CanonicalAssetType.FUTURES
        assert r2.side == CanonicalOrderSide.SELL
        assert r2.executed_qty == 2
        assert r2.executed_price == 350.50

    def test_lifecycle_connect_and_disconnect(self):
        """2. connect 및 disconnect에 따른 수신 계층 활성화 및 안전 종료 검증."""
        def mock_transport(method: str, path: str, headers: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
            if "token" in path:
                return {"access_token": "TEST_TOKEN", "expires_in": 3600}
            return {"rt_cd": "0", "output1": [{"odno": "001", "ccld_qty": "1", "ccld_pric": "2.0"}]}

        client = make_mock_client(mock_transport)
        adapter = RealBrokerAdapter(http_client=client)

        # 미연결 상태에서는 수신 안 됨
        assert adapter.is_connected() is False
        assert adapter.poll_execution_reports() == []

        # 연결 후 정상 수신
        assert adapter.connect() is True
        assert adapter.is_connected() is True
        assert adapter._listener_running is True
        reports = adapter.poll_execution_reports()
        assert len(reports) == 1

        # disconnect 후 수신 중지 및 자원 정리
        adapter.disconnect()
        assert adapter.is_connected() is False
        assert adapter._listener_running is False
        assert adapter.poll_execution_reports() == []

    def test_idempotency_duplicate_execution_records_filtered(self):
        """3. 동일 체결 레코드 다회 폴링 시 중복 반환 방어(Idempotency) 검증."""
        def mock_transport(method: str, path: str, headers: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
            if "token" in path:
                return {"access_token": "TEST_TOKEN", "expires_in": 3600}
            return {
                "rt_cd": "0",
                "output1": [
                    {"odno": "ORD-SAME", "ord_tmd": "100000", "ccld_qty": "3", "ccld_pric": "4.0", "pdno": "201V3350"},
                ],
            }

        client = make_mock_client(mock_transport)
        adapter = RealBrokerAdapter(http_client=client)
        adapter.connect()

        # 1차 폴링 -> 1건 수신
        first_poll = adapter.poll_execution_reports()
        assert len(first_poll) == 1
        assert first_poll[0].executed_qty == 3

        # 2차 폴링 -> 이미 처리된 동일 exec_id이므로 0건 반환 (중복 필터링)
        second_poll = adapter.poll_execution_reports()
        assert len(second_poll) == 0

    def test_inject_execution_report_queue(self):
        """4. inject_execution_report를 통한 WebSocket/외부 큐 주입 및 인출 검증."""
        client = make_mock_client(lambda m, p, h, b: {"access_token": "T", "expires_in": 3600, "rt_cd": "0", "output1": []})
        adapter = RealBrokerAdapter(http_client=client)
        adapter.connect()

        manual_rep = CanonicalExecutionReport(
            exec_id="EXEC-MANUAL-001",
            client_order_id="ORD-CLI-001",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            executed_qty=5,
            executed_price=3.2,
            fee=0.0,
            slippage=0.0,
            timestamp="2026-08-31 09:30:00",
            symbol="201V3350",
        )
        adapter.inject_execution_report(manual_rep)

        reports = adapter.poll_execution_reports()
        assert len(reports) == 1
        assert reports[0].exec_id == "EXEC-MANUAL-001"

    def test_end_to_end_runtime_consumption_and_fsm_update(self):
        """5. poll_execution_reports() -> OptionProgramRuntime.consume_execution_report() -> OrderRouter FSM 전이 연계 검증."""
        runtime = OptionProgramRuntime()
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-E2E-D11",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=10,
            price=3.5,
            symbol="201V3350",
        )
        token = RiskApprovalToken(
            order_id=uuid.uuid4(),
            timestamp_ns=1000000,
            signature="SIG-RISK-APPROVED-Track1-ORD-E2E-D11",
        )
        order_uuid = runtime.order_router.register_and_route(command=cmd, token=token)
        runtime._order_id_to_uuid[cmd.client_order_id] = order_uuid

        # 증권사 어댑터에서 체결 생성
        client = make_mock_client(
            lambda m, p, h, b: {
                "access_token": "T",
                "expires_in": 3600,
                "rt_cd": "0",
                "output1": [
                    {
                        "client_order_id": "ORD-E2E-D11",
                        "odno": "BRK-D11-01",
                        "ord_tmd": "110000",
                        "pdno": "201V3350",
                        "sll_buy_dvsn_cd": "02",
                        "ccld_qty": "10",
                        "ccld_pric": "3.5",
                    }
                ],
            }
        )
        adapter = RealBrokerAdapter(http_client=client)
        adapter.connect()

        # 수신 및 런타임 소비
        exec_reports = adapter.poll_execution_reports()
        assert len(exec_reports) == 1
        for rep in exec_reports:
            runtime.consume_execution_report(rep)

        # FSM 상태가 FILLED로 완결되었는지 확인
        assert runtime.order_router.fsm.get_status(order_uuid) == OrderStatus.FILLED
        assert runtime.get_order_executed_qty("ORD-E2E-D11") == 10

    def test_safe_error_handling_when_transport_fails(self):
        """6. API 통신 예외 발생 시 crash 없이 빈 리스트를 반환하는 안전성 검증."""
        def broken_transport(method: str, path: str, headers: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
            if "token" in path:
                return {"access_token": "T", "expires_in": 3600}
            raise ConnectionResetError("Broker socket forcibly closed by remote host")

        client = make_mock_client(broken_transport)
        adapter = RealBrokerAdapter(http_client=client)
        adapter.connect()

        # 예외가 발생해도 프로세스가 죽지 않고 빈 리스트 반환
        reports = adapter.poll_execution_reports()
        assert reports == []
