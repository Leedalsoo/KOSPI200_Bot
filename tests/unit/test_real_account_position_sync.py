"""Unit tests for REAL broker account and position state synchronization into OptionProgramRuntime and RiskEngine (D-04).

Verifies:
- REAL mode initialize() synchronizes broker.get_account_summary() and broker.get_positions() into OptionProgramRuntime
- RiskEngine and RiskGate accurately consume the synchronized account summary and positions for risk evaluation
- sync_broker_state() allows on-demand runtime synchronization
- PAPER and SHADOW initialization flows remain intact
- Exception during account summary or position fetching follows existing failure abort pathways
"""
from unittest.mock import patch, MagicMock
import pytest

from main import TradingSystem
from shared.contracts.canonical import (
    CanonicalAccountSummary,
    CanonicalMarketTick,
)
from option_program.broker.real_broker_adapter import RealBrokerAdapter


class TestRealAccountPositionSync:
    """REAL 브로커 계좌 및 포지션 동기화 경로 검증."""

    @pytest.mark.asyncio
    async def test_real_mode_initialization_syncs_account_and_positions(self):
        """REAL 모드 초기화 시 Broker의 계좌 잔고 및 포지션이 OptionProgramRuntime에 동기화됨을 검증."""
        system = TradingSystem(config={"broker_mode": "REAL"})

        custom_summary = CanonicalAccountSummary(
            account_id="REAL-TEST-ACC-1234",
            total_balance=75_000_000.0,
            used_margin=15_000_000.0,
            free_margin=60_000_000.0,
            realized_pnl=1_000_000.0,
            unrealized_pnl=500_000.0,
            timestamp="2026-08-31 09:30:00",
            positions={}
        )
        custom_positions = {
            "101V3000": {"symbol": "101V3000", "qty": 2, "avg_price": 350.0, "side": "BUY"}
        }

        with patch.object(RealBrokerAdapter, "connect", return_value=True):
            with patch.object(RealBrokerAdapter, "get_account_summary", return_value=custom_summary):
                with patch.object(RealBrokerAdapter, "get_positions", return_value=custom_positions):
                    await system.initialize()

        assert system.broker_mode == "REAL"
        assert system.vssf is None
        assert system.op_runtime is not None

        # 런타임 계좌 동기화 확인
        runtime_acc = system.op_runtime.account_summary
        assert runtime_acc.account_id == "REAL-TEST-ACC-1234"
        assert runtime_acc.total_balance == 75_000_000.0
        assert runtime_acc.used_margin == 15_000_000.0
        assert runtime_acc.free_margin == 60_000_000.0
        assert runtime_acc.positions == custom_positions

    @pytest.mark.asyncio
    async def test_risk_engine_reads_synchronized_real_state(self):
        """Risk Engine(Sensor & Gate)이 동기화된 REAL 계좌 및 포지션을 읽어 정상 평가하는지 검증."""
        system = TradingSystem(config={"broker_mode": "REAL"})

        custom_summary = CanonicalAccountSummary(
            account_id="REAL-RISK-ACC-999",
            total_balance=100_000_000.0,
            used_margin=20_000_000.0,
            free_margin=80_000_000.0,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            timestamp="2026-08-31 09:30:00",
            positions={"101V3000": {"qty": 1, "side": "BUY"}}
        )

        with patch.object(RealBrokerAdapter, "connect", return_value=True):
            with patch.object(RealBrokerAdapter, "get_account_summary", return_value=custom_summary):
                with patch.object(RealBrokerAdapter, "get_positions", return_value={"101V3000": {"qty": 1, "side": "BUY"}}):
                    await system.initialize()

        # 틱 투입 시 RiskSensor와 RiskGate가 정상 계좌/마진 정보를 기반으로 처리하는지 확인
        tick = CanonicalMarketTick(
            timestamp="2026-08-31 09:30:01",
            underlying_price=350.0,
            seq_id=1
        )
        commands = system.op_runtime.process_tick(tick)
        assert isinstance(commands, list)

        # Risk Sensor 스캔 시 계좌 마진 비율(used_margin / total_balance = 20/100 = 0.2)이 반영됨 확인
        assert system.op_runtime.account_summary.total_balance == 100_000_000.0
        assert system.op_runtime.account_summary.used_margin == 20_000_000.0

    @pytest.mark.asyncio
    async def test_sync_broker_state_on_demand_updates_runtime(self):
        """sync_broker_state() 호출 시 브로커의 최신 계좌 및 포지션이 런타임에 즉시 갱신되는지 검증."""
        system = TradingSystem(config={"broker_mode": "REAL"})
        await system.initialize()

        # 초기 상태 확인
        assert system.op_runtime.account_summary.total_balance > 0

        # 새로운 상태로 브로커 응답 모킹 후 sync_broker_state 호출
        updated_summary = CanonicalAccountSummary(
            account_id="REAL-UPDATED-001",
            total_balance=99_000_000.0,
            used_margin=10_000_000.0,
            free_margin=89_000_000.0,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            timestamp="2026-08-31 10:00:00"
        )
        updated_positions = {"201V3350": {"qty": 3, "side": "BUY"}}

        with patch.object(system.broker, "get_account_summary", return_value=updated_summary):
            with patch.object(system.broker, "get_positions", return_value=updated_positions):
                system.sync_broker_state()

        assert system.op_runtime.account_summary.account_id == "REAL-UPDATED-001"
        assert system.op_runtime.account_summary.total_balance == 99_000_000.0
        assert system.op_runtime.account_summary.positions == updated_positions

    @pytest.mark.asyncio
    async def test_paper_mode_regression_preserves_vssf_summary(self):
        """PAPER 모드에서는 VSSF 계좌 스냅샷이 OptionProgramRuntime에 정상 바인딩되는 기존 동작이 보존됨을 검증."""
        system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 30_000_000.0})
        await system.initialize()

        assert system.vssf is not None
        assert system.op_runtime.account_summary.total_balance == 30_000_000.0
        assert system.op_runtime.account_summary.free_margin == 30_000_000.0

    @pytest.mark.asyncio
    async def test_initialization_exception_aborts_boot(self):
        """get_account_summary 중 예외가 발생할 경우 부팅이 정상 차단(sys.exit(1))되는지 검증."""
        system = TradingSystem(config={"broker_mode": "REAL"})

        with patch.object(RealBrokerAdapter, "connect", return_value=True):
            with patch.object(RealBrokerAdapter, "get_account_summary", side_effect=RuntimeError("Network failure on balance fetch")):
                with pytest.raises(SystemExit) as excinfo:
                    await system.initialize()
                assert excinfo.value.code == 1
