# -*- coding: utf-8 -*-
import asyncio
import time
import logging
from enum import IntEnum
from typing import Callable, Awaitable, Dict, List, Any, Tuple

logger = logging.getLogger(__name__)

class EventPriority(IntEnum):
    EXECUTION = 0
    RISK = 1
    TICK = 2
    SYSTEM = 3

class EventBus:
    """HFT 비동기 이벤트 버스 (우선순위 큐 및 mmap 연동)"""
    
    def __init__(self) -> None:
        self._queue: asyncio.PriorityQueue[Tuple[int, float, str, Any]] = asyncio.PriorityQueue()
        self._subscribers: Dict[str, List[Callable[[Any], Awaitable[None]]]] = {}
        self._shared_memory: Any = None  # mmap 뼈대
        self._running: bool = False

    async def publish(self, priority: EventPriority, event_type: str, data: Any, timestamp: float = 0.0) -> None:
        """[목표 A] 이벤트를 튜플 형태로 우선순위 큐에 발행"""
        publish_time = timestamp if timestamp > 0 else time.time()
        # priority(int), timestamp(float) 순으로 정렬 보장
        await self._queue.put((int(priority), publish_time, event_type, data))

    def subscribe(self, event_type: str, callback: Callable[[Any], Awaitable[None]]) -> None:
        """[목표 A] 이벤트 타입별 비동기 콜백 등록"""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)

    async def process_events(self) -> None:
        """[목표 B] 무한 루프 처리, 200ms Stale 방어, 콜백 예외 격리, 기아 방지"""
        self._running = True
        while self._running:
            try:
                # 기아 방지 (Yield control to event loop)
                await asyncio.sleep(0)
                
                priority, timestamp, event_type, data = await self._queue.get()
                
                # 200ms 지연 데이터 Drop 로직 (Stale Data 방어 — Real-time 수신 모드에서만 판정)
                # 시뮬레이션 틱 타임스탬프와의 시간차 오차로 인한 무작위 Drop 방어
                now_wall = time.time()
                if timestamp > 0 and (now_wall - timestamp > 0.2) and (now_wall - timestamp < 86400.0):
                    logger.warning(f"Dropped stale event: {event_type} (delayed > 200ms)")
                    self._queue.task_done()
                    continue
                
                # 등록된 콜백 실행
                if event_type in self._subscribers:
                    for callback in self._subscribers[event_type]:
                        try:
                            # Zero-Copy 참조 무결성 강제 (data 그대로 전달)
                            await callback(data)
                        except Exception as e:
                            # 콜백 예외 격리 (시스템 전체 다운 방지)
                            logger.error(f"Error in subscriber callback for {event_type}: {e}")
                
                self._queue.task_done()
            except asyncio.CancelledError:
                self._running = False
                break
            except Exception as e:
                logger.error(f"Unexpected error in event bus loop: {e}")
