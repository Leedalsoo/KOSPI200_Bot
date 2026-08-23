# -*- coding: utf-8 -*-
import time
import orjson
from typing import Dict, Any

class TokenBucket:
    """Lock-free 실시간 API 스로틀링 버킷"""
    def __init__(self, capacity: int, fill_rate: float) -> None:
        self.capacity: float = float(capacity)
        self.fill_rate: float = fill_rate
        self.tokens: float = float(capacity)
        self.last_update: float = time.monotonic()

    def consume(self, tokens_to_consume: float = 1.0) -> bool:
        """[목표 A] Lock-free 방식의 실시간 토큰 보충 및 소모 연산"""
        now = time.monotonic()
        time_passed = now - self.last_update
        
        # [레드팀 지령 2] float 정밀도 오염 방어를 위한 min 클램핑
        self.tokens = min(self.capacity, self.tokens + time_passed * self.fill_rate)
        self.last_update = now
        
        if self.tokens >= tokens_to_consume:
            self.tokens -= tokens_to_consume
            return True
        return False

class NetworkAgent:
    """증권사 API 주문 전송 라우터"""
    def __init__(self, bucket: TokenBucket) -> None:
        self.bucket: TokenBucket = bucket

    async def send_payload(self, payload: Dict[str, Any]) -> bool:
        """[목표 B] 버킷 검증 및 orjson 고속 직렬화 후 전송 대기"""
        if self.bucket.consume():
            # [레드팀 지령 3] 내장 json 금지, orjson.dumps 고속 직렬화 강제
            _serialized_payload: bytes = orjson.dumps(payload)
            # 여기서는 전송 대기(시뮬레이션) 성공으로 처리
            return True
        return False
