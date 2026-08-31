"""Unit tests for distinguishing real broker account query failures from valid zero-balance states (D-05).

Verifies:
- Disconnected broker raises RuntimeError on get_account_summary() rather than returning dummy 0-balance summary
- API error response (rt_cd != '0') raises RuntimeError
- Successful API response with valid zero balance (dnca_tot_amt='0') returns valid CanonicalAccountSummary with total_balance=0.0
- Missing required fields or non-numeric values in output1 raise RuntimeError
- Failed query during REAL startup prevents saving a fake 0-balance account in Runtime and aborts startup
- PAPER and SHADOW broker account queries remain unaffected
"""
from unittest.mock import patch, MagicMock
import pytest

from option_program.broker.real_broker_adapter import RealBrokerAdapter, RealBrokerConfig
from option_program.broker.broker_interface import PaperBrokerAdapter, ShadowBrokerAdapter
from main import TradingSystem


class TestRealBrokerAccountQuery:
    """REAL 계좌 조회 실패와 실제 0원 상태 분리 검증."""

    def _create_adapter(self, connected: bool = True) -> RealBrokerAdapter:
        cfg = RealBrokerConfig(
            app_key="TEST_KEY",
            app_secret="TEST_SECRET",
            account_no="12345678-01",
            is_simulation=True
        )
        adapter = RealBrokerAdapter(config=cfg)
        if connected:
            adapter._connected = True
        return adapter

    def test_disconnected_broker_raises_error_on_account_query(self):
        """연결되지 않은(disconnected) 상태에서 get_account_summary() 호출 시 RuntimeError 발생 검증."""
        adapter = self._create_adapter(connected=False)
        assert adapter.is_connected() is False

        with pytest.raises(RuntimeError) as excinfo:
            adapter.get_account_summary()
        assert "Broker is disconnected" in str(excinfo.value)

    def test_api_error_response_raises_error(self):
        """Broker API 응답의 rt_cd가 '0'이 아닐 경우 RuntimeError 발생 검증."""
        adapter = self._create_adapter(connected=True)

        error_response = {
            "rt_cd": "1",
            "msg_cd": "EGW00123",
            "msg1": "모의투자 시스템 점검 중입니다."
        }
        with patch.object(adapter.client, "request", return_value=error_response):
            with pytest.raises(RuntimeError) as excinfo:
                adapter.get_account_summary()
            assert "Account query failed" in str(excinfo.value)
            assert "EGW00123" in str(excinfo.value)

    def test_valid_zero_balance_returns_legitimate_summary(self):
        """성공 응답(rt_cd='0')에서 실제 잔액이 0원인 경우 정상적인 0원 CanonicalAccountSummary를 반환하는지 검증."""
        adapter = self._create_adapter(connected=True)

        zero_balance_resp = {
            "rt_cd": "0",
            "msg_cd": "APBK0013",
            "msg1": "조회 성공",
            "output1": {
                "dnca_tot_amt": "0",
                "tot_evlu_amt": "0",
                "evlu_pfls_smtl_amt": "0"
            }
        }
        with patch.object(adapter.client, "request", return_value=zero_balance_resp):
            summary = adapter.get_account_summary()

        assert summary.account_id == "12345678-01"
        assert summary.total_balance == 0.0
        assert summary.used_margin == 0.0
        assert summary.free_margin == 0.0
        assert summary.unrealized_pnl == 0.0

    def test_missing_required_field_raises_error(self):
        """필수 데이터(output1.dnca_tot_amt)가 누락된 경우 RuntimeError 발생 검증."""
        adapter = self._create_adapter(connected=True)

        invalid_resp = {
            "rt_cd": "0",
            "output1": {
                "tot_evlu_amt": "10000000"
                # dnca_tot_amt 누락
            }
        }
        with patch.object(adapter.client, "request", return_value=invalid_resp):
            with pytest.raises(RuntimeError) as excinfo:
                adapter.get_account_summary()
            assert "missing required field 'output1.dnca_tot_amt'" in str(excinfo.value)

    def test_invalid_numeric_data_raises_error(self):
        """숫자로 파싱할 수 없는 값이 포함된 경우 RuntimeError 발생 검증."""
        adapter = self._create_adapter(connected=True)

        corrupt_resp = {
            "rt_cd": "0",
            "output1": {
                "dnca_tot_amt": "NOT_A_NUMBER",
                "tot_evlu_amt": "0"
            }
        }
        with patch.object(adapter.client, "request", return_value=corrupt_resp):
            with pytest.raises(RuntimeError) as excinfo:
                adapter.get_account_summary()
            assert "Invalid account numeric data" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_startup_account_query_failure_aborts_without_storing_zero_state(self):
        """REAL 초기화 시 계좌 조회가 실패하면 0원 상태로 저장되지 않고 부팅이 중단(sys.exit(1))되는지 검증."""
        system = TradingSystem(config={"broker_mode": "REAL"})

        with patch.object(RealBrokerAdapter, "connect", return_value=True):
            with patch.object(
                RealBrokerAdapter,
                "get_account_summary",
                side_effect=RuntimeError("[RealBroker] Account query failed: [EGW0001] Service Unavailable")
            ):
                with pytest.raises(SystemExit) as excinfo:
                    await system.initialize()

                assert excinfo.value.code == 1
                # 런타임이 정상 초기화 완료 상태로 남지 않음
                assert system.op_runtime is None

    def test_paper_and_shadow_account_query_preservation(self):
        """PAPER 및 SHADOW 어댑터의 get_account_summary() 동작이 변경 없이 정상 유지됨을 검증."""
        paper = PaperBrokerAdapter(initial_capital=50_000_000.0)
        shadow = ShadowBrokerAdapter(initial_capital=30_000_000.0)

        paper_summary = paper.get_account_summary()
        assert paper_summary.total_balance == 50_000_000.0

        shadow_summary = shadow.get_account_summary()
        assert shadow_summary.total_balance == 30_000_000.0
