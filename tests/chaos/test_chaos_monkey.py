# -*- coding: utf-8 -*-
import asyncio
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch
import pytest

from core.contracts import OrderRequest
from exchange.adapters.mock_broker import MockBrokerAdapter


@pytest.mark.asyncio
async def test_chaos_monkey_fault_injection_latency() -> None:
    """[카오스 검증] 카오스 모드 하에서 네트워크 지연이 정상 주입되는지 확인"""
    adapter = MockBrokerAdapter(chaos_mode=True, simulated_liquidity=100)
    req = OrderRequest(uuid.uuid4(), uuid.uuid4(), "CODE", Decimal("350.00"), 10, "BUY")

    # 2.5% 확률 조건 충족 -> sleep 실행
    with patch("random.random", return_value=0.01), patch("random.uniform", return_value=0.5):
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await adapter.send_order(req)
            mock_sleep.assert_called_once_with(0.5)


@pytest.mark.asyncio
async def test_chaos_monkey_fault_injection_timeout() -> None:
    """[카오스 검증] 카오스 모드 하에서 네트워크 타임아웃 예외가 고의 발생되는지 확인"""
    adapter = MockBrokerAdapter(chaos_mode=True, simulated_liquidity=100)
    req = OrderRequest(uuid.uuid4(), uuid.uuid4(), "CODE", Decimal("350.00"), 10, "BUY")

    # 5% 미만 조건 충족 -> TimeoutError 발생 확인
    with patch("random.random", return_value=0.03):
        with pytest.raises(asyncio.TimeoutError):
            await adapter.send_order(req)
