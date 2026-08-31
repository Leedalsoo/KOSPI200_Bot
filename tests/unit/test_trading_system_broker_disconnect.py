"""Unit tests for TradingSystem broker disconnection lifecycle in shutdown().

Verifies:
- Broker disconnect() is called exactly once during shutdown when broker is present
- Shutdown completes safely when broker is None
- Shutdown cleanup (GC enable, etc.) completes even if broker.disconnect() raises an exception
- No regressions in normal shutdown sequence across broker modes
"""
import gc
from unittest.mock import MagicMock
import pytest

from main import TradingSystem


class TestTradingSystemBrokerDisconnect:
    """TradingSystem.shutdown() 내 Broker.disconnect() 라이프사이클 계약 검증."""

    @pytest.mark.asyncio
    async def test_shutdown_calls_broker_disconnect_once(self):
        """broker 인스턴스가 존재할 때 shutdown 시 disconnect()가 정확히 1회 호출되는지 검증."""
        system = TradingSystem(config={"broker_mode": "PAPER"})
        await system.initialize()

        assert system.broker is not None
        assert system.broker.is_connected() is True

        mock_disconnect = MagicMock(wraps=system.broker.disconnect)
        system.broker.disconnect = mock_disconnect

        await system.shutdown()

        assert mock_disconnect.call_count == 1
        assert system.broker.is_connected() is False
        assert gc.isenabled() is True

    @pytest.mark.asyncio
    async def test_shutdown_safe_when_broker_is_none(self):
        """broker가 None인 상태(초기화 전 또는 실패 상태)에서도 shutdown이 에러 없이 안전하게 완료되는지 검증."""
        system = TradingSystem(config={"broker_mode": "PAPER"})
        assert system.broker is None

        # broker=None 상태에서 shutdown 호출
        await system.shutdown()

        assert gc.isenabled() is True

    @pytest.mark.asyncio
    async def test_shutdown_continues_cleanup_on_broker_disconnect_exception(self):
        """broker.disconnect()에서 예외가 발생하더라도 후속 정리(GC 복구 등)가 중단 없이 완료되는지 검증."""
        system = TradingSystem(config={"broker_mode": "PAPER"})
        await system.initialize()

        # disconnect 시 강제 예외 발생하도록 Mocking
        mock_broker = MagicMock()
        mock_broker.disconnect.side_effect = RuntimeError("Forced broker disconnect network fault")
        system.broker = mock_broker

        # GC를 명시적으로 disable 상태로 두고 shutdown 호출 후 enable 복구 확인
        gc.disable()
        assert gc.isenabled() is False

        await system.shutdown()

        # 예외가 발생했어도 disconnect()는 1회 호출되었고, GC는 정상 복구됨
        assert mock_broker.disconnect.call_count == 1
        assert gc.isenabled() is True

    @pytest.mark.asyncio
    async def test_shadow_mode_shutdown_disconnect_lifecycle(self):
        """SHADOW 모드에서도 shutdown 시 broker.disconnect()가 정상 호출되어 연결 해제되는지 검증."""
        system = TradingSystem(config={"broker_mode": "SHADOW"})
        await system.initialize()

        assert system.broker is not None
        assert system.broker.is_connected() is True

        await system.shutdown()

        assert system.broker.is_connected() is False
        assert gc.isenabled() is True
