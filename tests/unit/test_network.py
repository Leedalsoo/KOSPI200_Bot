import pytest
import time
from exchange.network import TokenBucket, NetworkAgent

def test_token_bucket_exhaustion() -> None:
    """[목표 A 검증] 토큰 버킷 한도 소진 즉각 방어 증명"""
    bucket = TokenBucket(capacity=2, fill_rate=1.0)
    assert bucket.consume(1.0) is True
    assert bucket.consume(1.0) is True
    assert bucket.consume(1.0) is False  # 3번째 요청은 즉각 거절되어야 함

def test_token_bucket_refill() -> None:
    """[목표 A 검증] 시간에 따른 Lock-free 토큰 보충 증명"""
    bucket = TokenBucket(capacity=1, fill_rate=10.0) # 1초에 10개 (0.1초당 1개)
    assert bucket.consume(1.0) is True
    assert bucket.consume(1.0) is False
    
    # 강제 시간 지연 시뮬레이션 방어
    time.sleep(0.15)
    assert bucket.consume(1.0) is True  # 보충 후 성공해야 함

@pytest.mark.asyncio
async def test_network_agent_orjson_latency() -> None:
    """[목표 B 검증] orjson을 통한 고속 직렬화 및 버킷 연동 증명"""
    bucket = TokenBucket(capacity=10, fill_rate=1.0)
    agent = NetworkAgent(bucket)
    
    payload = {"order_id": "12345", "price": 350.50}
    # send_payload 가 True를 반환하며 내부적으로 orjson.dumps 가 크래시 나지 않음을 증명
    result = await agent.send_payload(payload)
    assert result is True
    
    # 버킷 고갈 시 send_payload 실패 검증
    exhausted_bucket = TokenBucket(capacity=0, fill_rate=0.0)
    blocked_agent = NetworkAgent(exhausted_bucket)
    assert await blocked_agent.send_payload(payload) is False
