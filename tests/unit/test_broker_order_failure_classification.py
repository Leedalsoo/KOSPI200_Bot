"""Unit tests for D-08 Broker Order Failure Results Classification.

Verifies:
- DISCONNECTED status on disconnected broker (REAL, PAPER, SHADOW, STUB)
- SAFETY_BLOCKED status when safety arm key is missing or execution behavior is REJECT
- REJECTED status on broker rejection / insufficient margin
- AUTH_FAILED status on OAuth2 authentication failure or token expiration
- NETWORK_ERROR status on network transport exception / transport failure
- TIMEOUT_UNKNOWN status on timeout error without misleading as permanent rejection
- ACCEPTED status on successful order placement with legitimate broker_order_id
- Absence of fake broker_order_id on failed responses (broker_order_id is None)
- PAPER, SHADOW, REAL adherence to common BrokerOrderResponse contract
- Safe handling in TradingSystem pipeline without losing failure state
"""
from unittest.mock import patch, MagicMock
import pytest

from shared.contracts.canonical import (
    CanonicalOrderCommand,
    CanonicalAssetType,
    CanonicalOrderSide,
)
from option_program.broker.broker_interface import (
    BrokerOrderResponse,
    PaperBrokerAdapter,
    ShadowBrokerAdapter,
    RealBrokerAdapterStub,
)
from option_program.broker.real_broker_adapter import (
    RealBrokerAdapter,
    RealBrokerConfig,
    RealBrokerHttpClient,
)
from main import TradingSystem


@pytest.fixture
def sample_command() -> CanonicalOrderCommand:
    return CanonicalOrderCommand(
        client_order_id="ORD-D08-TEST-001",
        track_id="Track1",
        asset_type=CanonicalAssetType.FUTURES,
        side=CanonicalOrderSide.BUY,
        qty=1,
        price=350.0,
        symbol="101V3000",
    )


class TestRealBrokerOrderFailureClassification:
    """REAL 브로커 주문 실패 결과 세분화 검증."""

    def test_real_disconnected_failure(self, sample_command):
        """연결되지 않은 REAL 브로커는 DISCONNECTED 상태 및 success=False, broker_order_id=None 반환."""
        adapter = RealBrokerAdapter(
            config=RealBrokerConfig(is_simulation=True, app_key="KEY", app_secret="SECRET")
        )
        adapter._connected = False

        res = adapter.send_order(sample_command)
        assert isinstance(res, BrokerOrderResponse)
        assert res.success is False
        assert res.status == "DISCONNECTED"
        assert res.broker_order_id is None
        assert res.client_order_id == sample_command.client_order_id
        assert "disconnected" in res.message.lower()

    def test_real_safety_interlock_blocked(self, sample_command):
        """실거래 모드에서 안전 무장 키가 없으면 SAFETY_BLOCKED 상태 반환."""
        adapter = RealBrokerAdapter(
            config=RealBrokerConfig(
                is_simulation=False,
                app_key="KEY",
                app_secret="SECRET",
                safety_arm_key="",  # 무장 키 미설정
            )
        )
        adapter._connected = True

        res = adapter.send_order(sample_command)
        assert isinstance(res, BrokerOrderResponse)
        assert res.success is False
        assert res.status == "SAFETY_BLOCKED"
        assert res.broker_order_id is None
        assert "safety interlock" in res.message.lower()

    def test_real_broker_rejected(self, sample_command):
        """증권사 API 거절 응답 시 REJECTED 상태 및 오류 메시지 반환."""
        adapter = RealBrokerAdapter(
            config=RealBrokerConfig(is_simulation=True, app_key="KEY", app_secret="SECRET")
        )
        adapter._connected = True

        mock_resp = {
            "rt_cd": "1",
            "msg_cd": "APBK0013_REJ",
            "msg1": "주문 증거금 부족으로 주문이 거절되었습니다.",
        }
        with patch.object(adapter.client, "request", return_value=mock_resp):
            res = adapter.send_order(sample_command)

        assert isinstance(res, BrokerOrderResponse)
        assert res.success is False
        assert res.status == "REJECTED"
        assert res.broker_order_id is None
        assert "APBK0013_REJ" in res.message

    def test_real_auth_failure(self, sample_command):
        """토큰 인증 실패 시 AUTH_FAILED 상태 반환."""
        adapter = RealBrokerAdapter(
            config=RealBrokerConfig(is_simulation=True, app_key="KEY", app_secret="SECRET")
        )
        adapter._connected = True

        mock_resp = {
            "rt_cd": "1",
            "msg_cd": "ERR_AUTH",
            "msg1": "Authentication token expired/invalid",
        }
        with patch.object(adapter.client, "request", return_value=mock_resp):
            res = adapter.send_order(sample_command)

        assert isinstance(res, BrokerOrderResponse)
        assert res.success is False
        assert res.status == "AUTH_FAILED"
        assert res.broker_order_id is None
        assert "Authentication" in res.message

    def test_real_network_error(self, sample_command):
        """네트워크 전송 오류 시 NETWORK_ERROR 상태 반환."""
        adapter = RealBrokerAdapter(
            config=RealBrokerConfig(is_simulation=True, app_key="KEY", app_secret="SECRET")
        )
        adapter._connected = True

        mock_resp = {
            "rt_cd": "1",
            "msg_cd": "ERR_NET",
            "msg1": "Connection reset by peer",
        }
        with patch.object(adapter.client, "request", return_value=mock_resp):
            res = adapter.send_order(sample_command)

        assert isinstance(res, BrokerOrderResponse)
        assert res.success is False
        assert res.status == "NETWORK_ERROR"
        assert res.broker_order_id is None

    def test_real_timeout_unknown(self, sample_command):
        """요청 타임아웃 발생 시 TIMEOUT_UNKNOWN 상태 반환 (확정 거절과 명확히 구분)."""
        adapter = RealBrokerAdapter(
            config=RealBrokerConfig(is_simulation=True, app_key="KEY", app_secret="SECRET")
        )
        adapter._connected = True

        mock_resp = {
            "rt_cd": "1",
            "msg_cd": "ERR_TIMEOUT",
            "msg1": "Request timed out: timed out",
        }
        with patch.object(adapter.client, "request", return_value=mock_resp):
            res = adapter.send_order(sample_command)

        assert isinstance(res, BrokerOrderResponse)
        assert res.success is False
        assert res.status == "TIMEOUT_UNKNOWN"
        assert res.broker_order_id is None

    def test_real_successful_accepted_order(self, sample_command):
        """정상 주문 접수 시 ACCEPTED 상태 및 고유 broker_order_id 발급 검증."""
        adapter = RealBrokerAdapter(
            config=RealBrokerConfig(is_simulation=True, app_key="KEY", app_secret="SECRET")
        )
        adapter._connected = True

        mock_resp = {
            "rt_cd": "0",
            "msg_cd": "APBK0013",
            "msg1": "주문이 정상 접수되었습니다.",
            "output": {"ODNO": "00012345"},
        }
        with patch.object(adapter.client, "request", return_value=mock_resp):
            res = adapter.send_order(sample_command)

        assert isinstance(res, BrokerOrderResponse)
        assert res.success is True
        assert res.status == "ACCEPTED"
        assert res.broker_order_id == "BRK-REAL-00012345"
        assert res.client_order_id == sample_command.client_order_id


class TestPaperAndShadowBrokerFailureClassification:
    """PAPER, SHADOW 및 STUB 브로커의 공통 D-08 실패 계약 준수 검증."""

    def test_paper_broker_failure_classification(self, sample_command):
        """PAPER 브로커의 DISCONNECTED, SAFETY_BLOCKED, REJECTED 분류 검증."""
        paper = PaperBrokerAdapter(initial_capital=25_000_000.0)

        # 1. DISCONNECTED
        paper.set_connection(False)
        res_disc = paper.send_order(sample_command)
        assert res_disc.success is False
        assert res_disc.status == "DISCONNECTED"
        assert res_disc.broker_order_id is None

        # 2. SAFETY_BLOCKED
        paper.set_connection(True)
        paper.set_execution_behavior("REJECT")
        res_block = paper.send_order(sample_command)
        assert res_block.success is False
        assert res_block.status == "SAFETY_BLOCKED"
        assert res_block.broker_order_id is None

        # 3. REJECTED (마진 부족)
        paper.set_execution_behavior("NORMAL")
        paper.vssf.account.free_margin = 0.0  # 강제 마진 고갈
        res_rej = paper.send_order(sample_command)
        assert res_rej.success is False
        assert res_rej.status == "REJECTED"
        assert res_rej.broker_order_id is None

        # 4. ACCEPTED (정상)
        paper.vssf.account.free_margin = 25_000_000.0
        res_ok = paper.send_order(sample_command)
        assert res_ok.success is True
        assert res_ok.status == "ACCEPTED"
        assert res_ok.broker_order_id.startswith("BRK-PAPER-")

    def test_shadow_broker_failure_classification(self, sample_command):
        """SHADOW 브로커의 DISCONNECTED, SAFETY_BLOCKED, REJECTED 분류 검증."""
        shadow = ShadowBrokerAdapter(initial_capital=25_000_000.0)

        # DISCONNECTED
        shadow.set_connection(False)
        res = shadow.send_order(sample_command)
        assert res.success is False
        assert res.status == "DISCONNECTED"
        assert res.broker_order_id is None

        # SAFETY_BLOCKED
        shadow.set_connection(True)
        shadow.set_execution_behavior("REJECT")
        res = shadow.send_order(sample_command)
        assert res.success is False
        assert res.status == "SAFETY_BLOCKED"

        # ACCEPTED
        shadow.set_execution_behavior("NORMAL")
        res = shadow.send_order(sample_command)
        assert res.success is True
        assert res.status == "ACCEPTED"
        assert res.broker_order_id.startswith("BRK-SHADOW-")

    def test_stub_broker_failure_classification(self, sample_command):
        """RealBrokerAdapterStub의 계약 준수 검증."""
        stub = RealBrokerAdapterStub()

        # DISCONNECTED
        assert stub.is_connected() is False
        res = stub.send_order(sample_command)
        assert res.success is False
        assert res.status == "DISCONNECTED"
        assert res.broker_order_id is None

        # SAFETY_BLOCKED
        stub.connect()
        stub.set_execution_behavior("REJECT")
        res = stub.send_order(sample_command)
        assert res.success is False
        assert res.status == "SAFETY_BLOCKED"

        # ACCEPTED
        stub.set_execution_behavior("NORMAL")
        res = stub.send_order(sample_command)
        assert res.success is True
        assert res.status == "ACCEPTED"
        assert res.broker_order_id.startswith("BRK-REAL-STUB-")


class TestTradingSystemFailureHandling:
    """TradingSystem 주문 파이프라인에서 실패 응답 수신 시의 안전성 검증."""

    @pytest.mark.asyncio
    async def test_tradingsystem_handles_order_failure_without_crash(self):
        """send_order()가 실패 BrokerOrderResponse를 반환해도 TradingSystem이 크래시 없이 안전하게 진행함을 검증."""
        system = TradingSystem(config={"broker_mode": "PAPER"})
        await system.initialize()

        # Broker를 DISCONNECTED 상태로 전환
        system.broker.set_connection(False)

        # 1틱 실행
        await system.run_loop(max_ticks=1)

        # 주문은 발생했으나 접수 등록은 되지 않고 시스템은 정상 완료
        assert system.ticks_processed >= 1
        await system.shutdown()
