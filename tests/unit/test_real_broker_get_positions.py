"""Unit tests for RealBrokerAdapter.get_positions() inquiry and normalization (D-07).

Verifies:
- Disconnected broker raises RuntimeError on get_positions() rather than returning a misleading empty dict
- API error response (rt_cd != '0') raises RuntimeError rather than masking failure as empty positions
- Legitimate empty response (output2=[]) returns empty dict {}
- Single and multi-position responses are correctly normalized to standard position contracts
- Invalid data types in position items raise RuntimeError
- Integration with OptionProgramRuntime.update_positions() and D-04/D-06 sync flow
- PAPER and SHADOW broker get_positions() remain unaffected
"""
from unittest.mock import patch
import pytest

from option_program.broker.real_broker_adapter import RealBrokerAdapter, RealBrokerConfig
from option_program.broker.broker_interface import PaperBrokerAdapter, ShadowBrokerAdapter
from option_program.runtime.program_runtime import OptionProgramRuntime
from main import TradingSystem


class TestRealBrokerGetPositions:
    """REAL 브로커 포지션 조회 및 정규화 검증."""

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

    def test_disconnected_broker_raises_error_on_positions_query(self):
        """연결되지 않은(disconnected) 상태에서 get_positions() 호출 시 RuntimeError 발생 검증."""
        adapter = self._create_adapter(connected=False)
        assert adapter.is_connected() is False

        with pytest.raises(RuntimeError) as excinfo:
            adapter.get_positions()
        assert "Broker is disconnected" in str(excinfo.value)

    def test_api_error_response_raises_error_without_masking_as_empty_dict(self):
        """Broker API 에러 응답(rt_cd != '0') 시 빈 dict {}가 아닌 RuntimeError 발생 검증."""
        adapter = self._create_adapter(connected=True)

        error_response = {
            "rt_cd": "1",
            "msg_cd": "EGW00500",
            "msg1": "서버 내부 오류로 잔고 조회가 실패했습니다."
        }
        with patch.object(adapter.client, "request", return_value=error_response):
            with pytest.raises(RuntimeError) as excinfo:
                adapter.get_positions()
            assert "Position query failed" in str(excinfo.value)
            assert "EGW00500" in str(excinfo.value)

    def test_valid_empty_position_response_returns_empty_dict(self):
        """포지션이 없는 정상 성공 응답(output2=[])의 경우 정상적인 빈 dict {} 반환 검증."""
        adapter = self._create_adapter(connected=True)

        empty_resp = {
            "rt_cd": "0",
            "msg_cd": "APBK0013",
            "msg1": "조회 성공",
            "output1": {"dnca_tot_amt": "50000000"},
            "output2": []
        }
        with patch.object(adapter.client, "request", return_value=empty_resp):
            positions = adapter.get_positions()

        assert positions == {}
        assert isinstance(positions, dict)

    def test_single_and_multi_position_normalization(self):
        """단일 및 복수 포지션 API 응답의 규격 정규화 검증."""
        adapter = self._create_adapter(connected=True)

        multi_pos_resp = {
            "rt_cd": "0",
            "msg_cd": "APBK0013",
            "msg1": "조회 성공",
            "output2": [
                {
                    "pdno": "101V3000",
                    "cclt_qty": "2",
                    "sll_buy_dvsn_cd": "02",  # BUY
                    "pchs_avg_pric": "352.50",
                    "evlu_pfls_amt": "500000"
                },
                {
                    "prdt_cd": "201V3350",
                    "hld_qty": "5",
                    "side": "01",              # SELL
                    "avg_price": "2.45",
                    "pnl": "-100000"
                }
            ]
        }
        with patch.object(adapter.client, "request", return_value=multi_pos_resp):
            positions = adapter.get_positions()

        assert len(positions) == 2
        assert "101V3000" in positions
        assert positions["101V3000"] == {
            "symbol": "101V3000",
            "qty": 2,
            "side": "BUY",
            "avg_price": 352.50,
            "pnl": 500000.0
        }

        assert "201V3350" in positions
        assert positions["201V3350"] == {
            "symbol": "201V3350",
            "qty": 5,
            "side": "SELL",
            "avg_price": 2.45,
            "pnl": -100000.0
        }

    def test_invalid_position_numeric_data_raises_error(self):
        """포지션 수량이나 가격이 숫자로 파싱 불가한 경우 RuntimeError 발생 검증."""
        adapter = self._create_adapter(connected=True)

        corrupt_resp = {
            "rt_cd": "0",
            "output2": [
                {
                    "pdno": "101V3000",
                    "cclt_qty": "INVALID_QTY"
                }
            ]
        }
        with patch.object(adapter.client, "request", return_value=corrupt_resp):
            with pytest.raises(RuntimeError) as excinfo:
                adapter.get_positions()
            assert "Invalid numeric data in position item" in str(excinfo.value)

    def test_runtime_update_positions_integration(self):
        """정규화된 포지션 데이터가 OptionProgramRuntime.update_positions()에 완벽히 주입되는지 검증."""
        runtime = OptionProgramRuntime()
        assert runtime.account_summary.positions == {}

        normalized_positions = {
            "101V3000": {"symbol": "101V3000", "qty": 3, "side": "BUY", "avg_price": 350.0, "pnl": 0.0}
        }
        runtime.update_positions(normalized_positions)

        assert runtime.account_summary.positions == normalized_positions
        assert runtime.last_position_sync_time is not None
        assert runtime.is_position_state_stale() is False

    @pytest.mark.asyncio
    async def test_d04_real_sync_broker_state_integration(self):
        """TradingSystem.sync_broker_state() 실행 시 REAL broker.get_positions()가 런타임에 동기화되는지 검증."""
        system = TradingSystem(config={"broker_mode": "REAL"})
        await system.initialize()

        test_positions = {
            "101V3000": {"symbol": "101V3000", "qty": 1, "side": "BUY", "avg_price": 350.0, "pnl": 0.0}
        }
        with patch.object(system.broker, "get_positions", return_value=test_positions):
            system.sync_broker_state()

        assert system.op_runtime.account_summary.positions == test_positions
        assert system.op_runtime.is_position_state_stale() is False

    def test_paper_and_shadow_get_positions_preservation(self):
        """PAPER 및 SHADOW 어댑터의 get_positions() 동작이 정상 보존되는지 검증."""
        paper = PaperBrokerAdapter()
        shadow = ShadowBrokerAdapter()

        paper.vssf.account.position_mgr.positions["101V3000"] = {"symbol": "101V3000", "qty": 1, "side": "BUY"}
        shadow.vssf.account.position_mgr.positions["201V3350"] = {"symbol": "201V3350", "qty": 2, "side": "SELL"}

        assert "101V3000" in paper.get_positions()
        assert "201V3350" in shadow.get_positions()
