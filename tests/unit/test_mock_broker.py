import pytest
import uuid
import asyncio
from unittest.mock import patch, AsyncMock
from decimal import Decimal
from core.contracts import OrderRequest, ExecutionReport, OrderStatus
from exchange.adapters.mock_broker import MockBrokerAdapter

@pytest.mark.asyncio
async def test_mock_broker_full_signature_compliance() -> None:
    """[목표 A 검증] 필수 파라미터 누락 없이 ExecutionReport가 정상 생성되는지 증명"""
    adapter = MockBrokerAdapter(chaos_mode=False)
    req = OrderRequest(uuid.uuid4(), uuid.uuid4(), "CODE", Decimal("350.00"), 10, "BUY")
    
    report = await adapter.send_order(req)
    
    assert isinstance(report, ExecutionReport)
    assert report.fill_id != ""
    assert isinstance(report.raw_response, dict)
    assert report.status in (OrderStatus.FILLED, OrderStatus.PARTIAL)

@pytest.mark.asyncio
async def test_mock_broker_liquidity_clamping() -> None:
    """[목표 B 검증] 가상 유동성(50)을 초과하는 100계약 주문 시 50으로 클램핑 및 PARTIAL 처리 증명"""
    adapter = MockBrokerAdapter(chaos_mode=False, simulated_liquidity=50)
    req = OrderRequest(uuid.uuid4(), uuid.uuid4(), "CODE", Decimal("350.00"), 100, "BUY")
    
    report = await adapter.send_order(req)
    
    assert report.filled_qty == 50
    assert report.remaining_qty == 50
    assert report.status == OrderStatus.PARTIAL

@pytest.mark.asyncio
async def test_mock_broker_chaos_monkey() -> None:
    """[목표 C 검증] Chaos 모드 활성화 시 네트워크 딜레이(asyncio.sleep) 동작 증명"""
    adapter = MockBrokerAdapter(chaos_mode=True, simulated_liquidity=100)
    req = OrderRequest(uuid.uuid4(), uuid.uuid4(), "CODE", Decimal("350.00"), 10, "BUY")
    
    # random.random을 항상 0.01로 패치 (2.5% 확률 조건 충족 -> sleep 실행)
    # random.uniform을 항상 0.5로 패치
    with patch("random.random", return_value=0.01), patch("random.uniform", return_value=0.5):
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await adapter.send_order(req)
            mock_sleep.assert_called_once_with(0.5)

@pytest.mark.asyncio
async def test_mock_broker_chaos_monkey_timeout() -> None:
    """[목표 C 추가 검증] Chaos 모드 활성화 시 타임아웃 예외 동작 증명"""
    adapter = MockBrokerAdapter(chaos_mode=True, simulated_liquidity=100)
    req = OrderRequest(uuid.uuid4(), uuid.uuid4(), "CODE", Decimal("350.00"), 10, "BUY")
    
    # random.random을 항상 0.03으로 패치 (5% 미만 조건 충족 -> TimeoutError)
    with patch("random.random", return_value=0.03):
        with pytest.raises(asyncio.TimeoutError):
            await adapter.send_order(req)
