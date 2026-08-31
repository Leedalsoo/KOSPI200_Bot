"""Unit tests for TradingSystem broker connection lifecycle enforcement in initialize().

Verifies:
- Broker connect() is called immediately after creation
- Successful connect() leads to complete TradingSystem initialization
- Failed connect() aborts initialization and prevents entry into run_loop()
- Existing PAPER and SHADOW initialization flows remain intact
"""
from unittest.mock import patch, MagicMock
import pytest

from main import TradingSystem
from option_program.broker.broker_interface import BrokerFactory, PaperBrokerAdapter, ShadowBrokerAdapter


class TestTradingSystemBrokerConnect:
    """TradingSystem.initialize() 내 Broker.connect() 라이프사이클 계약 검증."""

    @pytest.mark.asyncio
    async def test_paper_mode_connects_and_initializes_successfully(self):
        """기본 PAPER 모드에서 broker.connect()가 호출되고 정상 초기화 완료되는지 검증."""
        system = TradingSystem(config={"broker_mode": "PAPER"})

        orig_create_broker = BrokerFactory.create_broker
        created_broker = None

        def spy_create_broker(*args, **kwargs):
            nonlocal created_broker
            created_broker = orig_create_broker(*args, **kwargs)
            return created_broker

        with patch("main.BrokerFactory.create_broker", side_effect=spy_create_broker):
            await system.initialize()

        assert created_broker is not None
        assert isinstance(created_broker, PaperBrokerAdapter)
        assert system.broker is created_broker
        assert system.broker.is_connected() is True
        assert system.vms is not None
        assert system.op_runtime is not None
        assert system.vssf is not None

    @pytest.mark.asyncio
    async def test_shadow_mode_connects_and_initializes_successfully(self):
        """SHADOW 모드에서 broker.connect()가 호출되고 정상 초기화 완료되는지 검증."""
        system = TradingSystem(config={"broker_mode": "SHADOW"})

        orig_create_broker = BrokerFactory.create_broker
        created_broker = None

        def spy_create_broker(*args, **kwargs):
            nonlocal created_broker
            created_broker = orig_create_broker(*args, **kwargs)
            return created_broker

        with patch("main.BrokerFactory.create_broker", side_effect=spy_create_broker):
            await system.initialize()

        assert created_broker is not None
        assert isinstance(created_broker, ShadowBrokerAdapter)
        assert system.broker is created_broker
        assert system.broker.is_connected() is True
        assert system.vms is not None
        assert system.op_runtime is not None
        assert system.vssf is not None

    @pytest.mark.asyncio
    async def test_broker_connect_failure_aborts_initialization(self):
        """broker.connect()가 False를 반환할 때 sys.exit(1)로 초기화가 중단되고 컴포넌트가 완료 상태로 진행하지 않음을 검증."""
        system = TradingSystem(config={"broker_mode": "PAPER"})

        mock_broker = MagicMock()
        mock_broker.connect.return_value = False

        with patch("main.BrokerFactory.create_broker", return_value=mock_broker):
            with pytest.raises(SystemExit) as excinfo:
                await system.initialize()
            assert excinfo.value.code == 1

        # VMS와 op_runtime은 생성되지 않아 정상 초기화 완료 상태로 진행되지 않음
        assert system.vms is None
        assert system.op_runtime is None

    @pytest.mark.asyncio
    async def test_uninitialized_system_cannot_enter_run_loop(self):
        """초기화가 중단되거나 완료되지 않은 시스템은 run_loop() 호출 시 RuntimeError를 발생시킴을 검증."""
        system = TradingSystem(config={"broker_mode": "PAPER"})
        # initialize() 없이 또는 실패 상태에서 run_loop 호출
        with pytest.raises(RuntimeError, match="TradingSystem must be initialized before run_loop"):
            await system.run_loop(max_ticks=1)
