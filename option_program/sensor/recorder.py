# -*- coding: utf-8 -*-
import asyncio
import orjson
import logging
from typing import Any, Optional, List
from shared.core.bus import EventBus

class SensorRecorder:
    """비간섭(Zero-Interference) 실시간 텔레메트리 수집 센서"""
    
    def __init__(self, bus: EventBus, log_path: str) -> None:
        self.bus: EventBus = bus
        self.log_path: str = log_path
        # 🛡️ [메모리 폭발 방어] 큐 크기 maxsize=10000 으로 가드 설정
        self._queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=10000)
        self._logger: logging.Logger = logging.getLogger("SensorRecorder")
        self._worker_task: Optional[asyncio.Task[None]] = None
        self._is_running: bool = False

    async def start(self) -> None:
        """백그라운드 기록 태스크 시작"""
        self._is_running = True
        self._worker_task = asyncio.create_task(self._worker())

    async def stop(self) -> None:
        """백그라운드 기록 태스크 종료"""
        self._is_running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def _worker(self) -> None:
        """[목표 B, C] 비동기 큐를 비우며 배치 단위 적재"""
        while self._is_running:
            try:
                # 큐에서 첫 번째 항목을 비동기적으로 대기
                event = await self._queue.get()
                batch: List[Any] = [event]

                # 대기 중인 다른 이벤트가 있다면 최대 100개까지 배치로 묶어서 일괄 가져옴 (Cold Data 효율 적재)
                while len(batch) < 100:
                    try:
                        event = self._queue.get_nowait()
                        batch.append(event)
                    except asyncio.QueueEmpty:
                        break

                # 🛡️ [인코딩 무결성] wb 모드로 바이너리 직접 기록을 수행하여 인코딩 변환 오버헤드 0 차단
                with open(self.log_path, "ab") as f:
                    for item in batch:
                        payload = orjson.dumps(item, option=orjson.OPT_APPEND_NEWLINE)
                        f.write(payload)

                # 배치 내 모든 태스크에 대한 처리 완료 신호 발송
                for _ in range(len(batch)):
                    self._queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error("Error in SensorRecorder background worker: %s", str(e))
                await asyncio.sleep(0.01)

    async def on_event(self, event_data: Any) -> None:
        """[목표 A] 이벤트 수신 즉시 큐 적재 (지연 평가 로깅)"""
        # 🛡️ [지연 평가 로깅 준수] f-string 문자열 생성 비용을 절감하기 위해 % 서식 문자열 전달
        self._logger.debug("Received event data for telemetry: %s", event_data)

        try:
            self._queue.put_nowait(event_data)
        except asyncio.QueueFull:
            # 🛡️ [메모리 폭발 방어] 큐 포화 시 대기 블록하지 않고 이벤트를 드롭하며 경고 출력
            self._logger.warning("SensorRecorder queue is full. Dropping telemetry event: %s", event_data)
