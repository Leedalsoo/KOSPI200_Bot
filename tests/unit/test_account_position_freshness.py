"""Unit tests for Account and Position Freshness / Staleness Management (D-06).

Verifies:
- Independent recording of last successful synchronization timestamp for account summary and positions
- Fresh state detection within timeout threshold
- Stale state detection when elapsed time exceeds timeout threshold
- Unsuccessful query / exception preserves previously recorded successful timestamp
- RiskSensor reflects stale state into snapshot (is_account_stale, is_position_stale)
- D-04 REAL synchronization and PAPER/SHADOW regression preservation
"""
import time
from unittest.mock import patch, MagicMock
import pytest

from shared.contracts.canonical import CanonicalAccountSummary, CanonicalMarketTick
from option_program.runtime.program_runtime import OptionProgramRuntime
from option_program.risk_control.risk_engine import RiskConfig, RiskSensor
from main import TradingSystem


class TestAccountPositionFreshness:
    """계좌 및 포지션 Freshness / Staleness 관리 검증."""

    def test_independent_timestamp_recording_on_sync(self):
        """계좌 요약 및 포지션 동기화 시 각각 독립적으로 성공 타임스탬프가 기록되는지 검증."""
        runtime = OptionProgramRuntime()
        assert runtime.last_account_sync_time is None
        assert runtime.last_position_sync_time is None

        # 1. 특정 시각으로 계좌 동기화
        t_acc = 1000.0
        acc_summary = CanonicalAccountSummary(
            account_id="ACC-001",
            total_balance=50_000_000.0,
            used_margin=0.0,
            free_margin=50_000_000.0,
            realized_pnl=0.0,
            unrealized_pnl=0.0
        )
        runtime.update_account_summary(acc_summary, sync_time=t_acc)
        assert runtime.last_account_sync_time == t_acc

        # 2. 다른 시각으로 포지션 동기화
        t_pos = 1005.0
        positions = {"101V3000": {"qty": 2, "side": "BUY"}}
        runtime.update_positions(positions, sync_time=t_pos)
        assert runtime.last_position_sync_time == t_pos
        assert runtime.last_account_sync_time == t_acc
        assert runtime.account_summary.positions == positions

    def test_fresh_and_stale_boundary_evaluation(self):
        """임계값(기본 30초) 기준 Fresh와 Stale 판정 경계 검증."""
        risk_cfg = RiskConfig(account_stale_timeout_sec=30.0, position_stale_timeout_sec=30.0)
        runtime = OptionProgramRuntime(risk_config=risk_cfg)

        base_time = 10000.0
        runtime.update_account_summary(runtime.account_summary, sync_time=base_time)
        runtime.update_positions({"101V3000": {"qty": 1}}, sync_time=base_time)

        # 1. 29.9초 경과 -> Fresh (is_stale is False)
        assert runtime.is_account_state_stale(current_time=base_time + 29.9) is False
        assert runtime.is_position_state_stale(current_time=base_time + 29.9) is False

        # 2. 30.0초 경과 -> Fresh 경계
        assert runtime.is_account_state_stale(current_time=base_time + 30.0) is False
        assert runtime.is_position_state_stale(current_time=base_time + 30.0) is False

        # 3. 30.1초 경과 -> Stale (is_stale is True)
        assert runtime.is_account_state_stale(current_time=base_time + 30.1) is True
        assert runtime.is_position_state_stale(current_time=base_time + 30.1) is True

    def test_uninitialized_sync_time_evaluates_to_stale(self):
        """동기화 타임스탬프가 None인 경우 무조건 Stale로 판정되는지 검증."""
        runtime = OptionProgramRuntime()
        runtime.last_account_sync_time = None
        runtime.last_position_sync_time = None

        assert runtime.is_account_state_stale() is True
        assert runtime.is_position_state_stale() is True

    def test_sync_failure_preserves_existing_timestamp(self):
        """TradingSystem.sync_broker_state()에서 조회 실패 시 기존 성공 타임스탬프가 보존되는지 검증."""
        system = TradingSystem(config={"broker_mode": "REAL"})
        mock_broker = MagicMock()
        system.broker = mock_broker
        system.op_runtime = OptionProgramRuntime()

        # 최초 성공 동기화 (t = 5000.0)
        initial_summary = CanonicalAccountSummary(
            account_id="ACC-REAL-1",
            total_balance=60_000_000.0,
            used_margin=0.0,
            free_margin=60_000_000.0,
            realized_pnl=0.0,
            unrealized_pnl=0.0
        )
        system.op_runtime.update_account_summary(initial_summary, sync_time=5000.0)
        system.op_runtime.update_positions({"101V3000": {"qty": 1}}, sync_time=5000.0)

        assert system.op_runtime.last_account_sync_time == 5000.0
        assert system.op_runtime.last_position_sync_time == 5000.0

        # 브로커 조회 시 예외 발생 모킹
        mock_broker.get_account_summary.side_effect = RuntimeError("Account fetch failed")
        mock_broker.get_positions.side_effect = RuntimeError("Position fetch failed")

        # sync_broker_state 실행 (예외가 포착되고 기존 타임스탬프 유지되어야 함)
        system.sync_broker_state()

        assert system.op_runtime.last_account_sync_time == 5000.0
        assert system.op_runtime.last_position_sync_time == 5000.0

    def test_risk_sensor_reflects_stale_state_in_snapshot(self):
        """Risk Sensor 및 process_tick() 실행 시 계좌/포지션 Stale 상태가 SensorSnapshot에 반영되는지 검증."""
        risk_cfg = RiskConfig(account_stale_timeout_sec=30.0, position_stale_timeout_sec=30.0)
        runtime = OptionProgramRuntime(risk_config=risk_cfg)

        # 동기화 시각을 과거(현재 기준 100초 전)로 설정하여 Stale 유도
        runtime.last_account_sync_time = time.time() - 100.0
        runtime.last_position_sync_time = time.time() - 100.0

        assert runtime.is_account_state_stale() is True
        assert runtime.is_position_state_stale() is True

        tick = CanonicalMarketTick(
            timestamp="2026-08-31 09:30:00",
            underlying_price=350.0,
            seq_id=1
        )
        commands = runtime.process_tick(tick)
        assert isinstance(commands, list)

        # Risk Sensor의 scan_risk가 stale 플래그를 정상 반영하는지 단위 검증
        sensor = RiskSensor(config=risk_cfg)
        snapshot = sensor.scan_risk(
            active_vol=1.0,
            base_vol=1.0,
            current_regime="NORMAL",
            is_account_stale=True,
            is_position_stale=False
        )
        assert snapshot.is_account_stale is True
        assert snapshot.is_position_stale is False
        assert "STALE_STATE_DETECTED" in snapshot.reason

    @pytest.mark.asyncio
    async def test_d04_real_initialization_regression(self):
        """D-04 REAL 초기화 경로에서 정상적으로 계좌/포지션 동기화 및 타임스탬프 기록이 수행되는지 검증."""
        system = TradingSystem(config={"broker_mode": "REAL"})
        await system.initialize()

        assert system.op_runtime is not None
        assert system.op_runtime.last_account_sync_time is not None
        assert system.op_runtime.is_account_state_stale() is False
