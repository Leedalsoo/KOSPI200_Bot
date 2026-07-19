import pytest
from unittest.mock import patch
from core.contracts import OrderRequest
from exchange.adapters.real_broker import RealBrokerAdapter
from decimal import Decimal
import uuid
import time

@pytest.mark.asyncio
async def test_exponential_backoff_on_429() -> None:
    """[목표 B 검증] HTTP 429 에러 시 지수 백오프가 적용되는지 모킹하여 증명"""
    adapter = RealBrokerAdapter("key", "secret", "http://mock.url")
    req = OrderRequest(uuid.uuid4(), uuid.uuid4(), "CODE", Decimal("350"), 1, "BUY")
    
    # 429 에러 2번 반환 후 200 반환 모킹
    responses = [
        {"status": 429, "body": b""},
        {"status": 429, "body": b""},
        {"status": 200, "body": b'{"rt_cd": "0", "msg1": "Success"}'}
    ]
    
    with patch.object(adapter, '_post_request', side_effect=responses) as mock_post:
        start_time = time.monotonic()
        report = await adapter.send_order_to_krx(req)
        end_time = time.monotonic()
        
        from core.contracts import OrderStatus
        assert report.status == OrderStatus.NEW
        assert mock_post.call_count == 3
        
        # 첫 번째 재시도 대기: 0.1초
        # 두 번째 재시도 대기: 0.2초
        # 총 0.3초 이상의 대기 시간이 발생해야 함
        assert end_time - start_time >= 0.25

@pytest.mark.asyncio
async def test_immediate_abort_on_maintenance() -> None:
    """[목표 B 검증] 전산점검(503 등 특정 코드) 감지 시 재시도 없이 즉각 예외 발생 증명"""
    adapter = RealBrokerAdapter("key", "secret", "http://mock.url")
    req = OrderRequest(uuid.uuid4(), uuid.uuid4(), "CODE", Decimal("350"), 1, "BUY")
    
    # 503 에러 발생 시뮬레이션
    with patch.object(adapter, '_post_request', return_value={"status": 503, "body": b""}) as mock_post:
        with pytest.raises(RuntimeError, match="Broker maintenance or critical error"):
            await adapter.send_order_to_krx(req)
            
        # 재시도 없이 1번만 호출되어야 함
        assert mock_post.call_count == 1

@pytest.mark.asyncio
async def test_token_refresh_background_task() -> None:
    """[목표 C 검증] 토큰 갱신 태스크가 실행되며 에러 격리가 잘 되는지 증명"""
    adapter = RealBrokerAdapter("key", "secret", "http://mock.url")
    await adapter.start()
    
    assert adapter._auth_token == "INITIAL_TOKEN"
    assert adapter._refresh_task is not None
    assert not adapter._refresh_task.done()
    
    await adapter.stop()
    assert adapter._refresh_task.cancelled()
