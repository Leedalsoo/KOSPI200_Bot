# -*- coding: utf-8 -*-
import asyncio
import logging
from typing import Any, Dict, Optional
from uuid import uuid4

import orjson

logger = logging.getLogger(__name__)

# 백프레셔 큐 최대 크기
_QUEUE_MAXSIZE: int = 1000
# Ping/Pong 타임아웃 (초)
_PING_INTERVAL: float = 20.0
_PONG_TIMEOUT: float = 10.0


class WebsocketBroadcaster:
    """대시보드 밀어내기 단방향 브로드캐스터 (Backpressure 적용)"""

    def __init__(self) -> None:
        # 세션 ID → 수신 큐
        self.connections: Dict[str, asyncio.Queue[bytes]] = {}
        # 세션 ID → websocket 객체
        self.active_websockets: Dict[str, Any] = {}
        # 세션 ID → 워커 태스크
        self._worker_tasks: Dict[str, asyncio.Task[None]] = {}

    async def register_connection(self, websocket: Any) -> str:
        """[목표 A, B] 새 연결 등록 및 세션 워커 태스크 시작"""
        session_id: str = str(uuid4())
        self.connections[session_id] = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
        self.active_websockets[session_id] = websocket
        # 개별 세션 워커 태스크 생성 (Ping/Pong 타임아웃 및 큐 처리 내장)
        task: asyncio.Task[None] = asyncio.create_task(
            self._connection_worker(session_id, websocket)
        )
        self._worker_tasks[session_id] = task
        logger.info("WebSocket session registered: %s", session_id)
        return session_id

    async def broadcast_event(self, event_data: Any) -> None:
        """[목표 C] orjson 직렬화 1회 수행 후 모든 활성 클라이언트 큐에 푸시"""
        # 🛡️ [직렬화 부하 방어] 직렬화는 루프 바깥에서 단 1회만 수행
        payload: bytes = orjson.dumps(event_data, default=str)

        dead_sessions: list[str] = []
        for session_id, queue in self.connections.items():
            if queue.full():
                # 🛡️ [백프레셔 Drop-Oldest 전략] 큐가 가득 찼으면 가장 오래된 항목을 제거
                try:
                    queue.get_nowait()
                    logger.warning(
                        "Backpressure: dropped oldest item for session %s", session_id
                    )
                except asyncio.QueueEmpty:
                    dead_sessions.append(session_id)
                    continue
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning(
                    "Backpressure: queue still full after drop for session %s", session_id
                )

        # 이미 닫힌 세션 정리
        for sid in dead_sessions:
            self._cleanup_session(sid)

    async def _connection_worker(self, session_id: str, websocket: Any) -> None:
        """[목표 A, B] 개별 세션의 큐 처리, 백프레셔 Drop-Oldest, Ping/Pong 타임아웃 감시"""
        queue: Optional[asyncio.Queue[bytes]] = self.connections.get(session_id)
        if queue is None:
            return

        try:
            while session_id in self.active_websockets:
                try:
                    # [목표 B] Ping 전송 후 pong 타임아웃 대기
                    await websocket.ping()
                    # _PONG_TIMEOUT 내에 큐에서 데이터 소진 후 다음 ping 주기까지 대기
                    deadline = asyncio.get_event_loop().time() + _PING_INTERVAL
                    while asyncio.get_event_loop().time() < deadline:
                        try:
                            # 남은 시간 내에서 큐 항목을 소진
                            remaining = max(0.0, deadline - asyncio.get_event_loop().time())
                            payload = await asyncio.wait_for(queue.get(), timeout=remaining)
                            # [목표 C] send_bytes 로 인코딩 오버헤드 0 달성
                            await websocket.send_bytes(payload)
                        except asyncio.TimeoutError:
                            # 큐가 비어 있으면 다음 ping 주기로 이동
                            break
                except asyncio.TimeoutError:
                    # 🛡️ [고아 세션 방어] Pong 미수신 → 세션 강제 종료
                    logger.warning(
                        "Ping/Pong timeout — forcing close for session %s", session_id
                    )
                    await websocket.close()
                    break
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "WebSocket error for session %s: %s", session_id, exc
                    )
                    break
        finally:
            # 🛡️ [메모리 누수 방어] 모든 종료 경로에서 세션 자원 즉시 회수
            self._cleanup_session(session_id)
            logger.info("WebSocket session cleaned up: %s", session_id)

    def _cleanup_session(self, session_id: str) -> None:
        """세션 관련 자원을 딕셔너리에서 즉시 제거"""
        self.connections.pop(session_id, None)
        self.active_websockets.pop(session_id, None)
        task = self._worker_tasks.pop(session_id, None)
        if task and not task.done():
            task.cancel()
