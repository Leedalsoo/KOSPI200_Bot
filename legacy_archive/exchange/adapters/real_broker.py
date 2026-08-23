# -*- coding: utf-8 -*-
import asyncio
import orjson
import logging
from typing import Dict, Any, Optional
from core.contracts import OrderRequest, ExecutionReport, OrderStatus
from decimal import Decimal
from datetime import datetime

logger = logging.getLogger(__name__)

class RealBrokerAdapter:
    """한국투자증권 Open API 기반 실거래 주문 패킷 주입 어댑터"""
    
    def __init__(self, api_key: str, api_secret: str, base_url: str):
        self.api_key: str = api_key
        self.api_secret: str = api_secret
        self.base_url: str = base_url
        self._auth_token: Optional[str] = None
        self._refresh_task: Optional[asyncio.Task[Any]] = None

    async def start(self) -> None:
        """어댑터 초기화 및 토큰 갱신 태스크 시작"""
        # 초기 토큰 발급 시뮬레이션
        self._auth_token = "INITIAL_TOKEN"
        
        loop = asyncio.get_running_loop()
        self._refresh_task = loop.create_task(self._refresh_token_task())
        logger.info("RealBrokerAdapter started, token refresh task initialized.")

    async def stop(self) -> None:
        """자원 해제 및 백그라운드 태스크 종료"""
        # [레드팀 지령 3] 메모리 누수 방어를 위한 고아 태스크 취소
        if self._refresh_task is not None and not self._refresh_task.done():
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
        logger.info("RealBrokerAdapter stopped.")

    async def _refresh_token_task(self) -> None:
        """[목표 C] 토큰 만료 5분 전 무중단 갱신 백그라운드 태스크"""
        try:
            while True:
                # 갱신 주기는 임의로 1초 대기 후 갱신(시뮬레이션)
                # 실제로는 토큰 만료 5분 전에 깨어나도록 설정
                await asyncio.sleep(3600)
                self._auth_token = "REFRESHED_TOKEN"
                logger.debug("Auth token refreshed.")
        except asyncio.CancelledError:
            logger.debug("Token refresh task cancelled.")
            raise

    # 모킹을 위한 내부 헬퍼 메서드 (실제 HTTP 클라이언트를 대체)
    async def _post_request(self, payload_bytes: bytes) -> Dict[str, Any]:
        """HTTP POST 모킹용 내부 메서드"""
        # 이 부분은 테스트에서 모킹됨
        return {"status": 200, "body": b'{"rt_cd": "0", "msg1": "Success"}'}

    async def send_order_to_krx(self, request: OrderRequest) -> ExecutionReport:
        """[목표 A, B] orjson 고속 직렬화 전송 및 지수 백오프/점검 감지 방어 로직"""
        # [레드팀 지령 3] orjson 강제 직렬화
        payload_dict = {
            "order_id": str(request.client_order_id),
            "symbol": request.instrument_code,
            "price": float(request.price),
            "quantity": request.qty,
            "side": request.side
        }
        payload_bytes: bytes = orjson.dumps(payload_dict)
        
        max_retries = 3
        base_delay = 0.1
        
        for attempt in range(max_retries):
            # 네트워크 통신 시뮬레이션 (Mocking point)
            response = await self._post_request(payload_bytes)
            status_code = response.get("status", 200)
            body_bytes = response.get("body", b"")
            
            if status_code == 200:
                # [레드팀 지령 1] orjson 파싱 에러 강건성
                try:
                    parsed = orjson.loads(body_bytes)
                except orjson.JSONDecodeError:
                    logger.error("Failed to parse broker response.")
                    raise RuntimeError("Invalid JSON response from broker")
                
                # ExecutionReport 조립 (단순화된 성공 응답)
                return ExecutionReport(
                    client_order_id=request.client_order_id,
                    broker_order_id="MOCK_BROKER_ID",
                    fill_id="MOCK_FILL_ID",
                    status=OrderStatus.NEW,
                    filled_qty=0,
                    filled_price=Decimal("0"),
                    remaining_qty=request.qty,
                    timestamp=datetime.now(),
                    raw_response=parsed
                )
            elif status_code == 429 or status_code == 500:
                # [목표 B] HTTP 429, 500 에러 시 지수 백오프
                if attempt == max_retries - 1:
                    raise RuntimeError(f"Max retries reached for status {status_code}")
                # [레드팀 지령 2] 단일 스레드 병목 차단을 위한 asyncio.sleep 사용
                delay = base_delay * (2 ** attempt)
                await asyncio.sleep(delay)
            elif status_code == 503 or (501 <= status_code <= 599):
                # [목표 B] 전산 점검 등 치명적 에러 감지 시 즉각 타임아웃
                raise RuntimeError(f"Broker maintenance or critical error: {status_code}")
            else:
                raise RuntimeError(f"Unexpected broker status code: {status_code}")
                
        raise RuntimeError("Failed to send order")
