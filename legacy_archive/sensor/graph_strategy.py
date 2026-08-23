# -*- coding: utf-8 -*-
"""
프론트엔드 시각화 전용 실시간 스트리머 (GraphStrategyObserver)
"""
import asyncio
from collections import deque
import time
from typing import Any, Dict, Optional
import orjson

class GraphStrategyObserver:
    """프론트엔드 시각화 전용 실시간 스트리머"""

    def __init__(self, input_queue: asyncio.Queue[Dict[str, Any]]) -> None:
        self.input_queue: asyncio.Queue[Dict[str, Any]] = input_queue
        # 🛡️ [자율적 가비지 관리] 버퍼 크기를 1000개로 한정하여 OOM 방어
        self.visual_buffer: deque[Dict[str, Any]] = deque(maxlen=1000)
        # 🛡️ [STANDBY_OVERRIDE 방어] 오라클 정지 신호 수신 플래그
        self.standby_mode: bool = False
        # 🛡️ [1Hz 샘플링 제한] 고주파 핫패스 부하 방지를 위한 최종 전송 타임스탬프
        self.last_send_time: float = 0.0
        # 🛡️ [테스트용 우회 플래그] 샘플링 주기를 무시하고 모든 값을 적재하기 위한 필터링 우회 속성
        self.bypass_sampling: bool = False
        # 비동기 루프 제어용
        self._running: bool = False
        self._loop_task: Optional[asyncio.Task[None]] = None

    def set_standby(self, state: bool) -> None:
        """STANDBY_OVERRIDE 상태 동기화 및 버퍼 제어"""
        self.standby_mode = state
        if state:
            # 셧다운 시 버퍼 즉각 클리어
            self.visual_buffer.clear()

    async def start(self) -> None:
        """관측기 루프 기동"""
        self._running = True
        self._loop_task = asyncio.create_task(self.run_observer())

    async def stop(self) -> None:
        """관측기 루프 안전 중지"""
        self._running = False
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass

    async def run_observer(self) -> None:
        """[목표 A] 데이터 수신 및 정제 루프"""
        while self._running:
            try:
                # 큐로부터 원시 지표 수신
                data = await self.input_queue.get()
                
                # 🛡️ [STANDBY_OVERRIDE 방어] standby 모드 시 수신 데이터 무시 및 즉각 버퍼 클리어
                if self.standby_mode:
                    self.visual_buffer.clear()
                    self.input_queue.task_done()
                    continue
                current_time = time.time()
                # 🛡️ [0.5Hz ~ 1Hz 샘플링 제한] 전송 간격을 최소 1.0초 이상으로 유지 (1Hz 이하). 단, bypass_sampling 또는 last_send_time이 0.0인 경우 허용
                if self.bypass_sampling or self.last_send_time == 0.0 or current_time - self.last_send_time >= 1.0:
                    # 데이터 정제 및 패키징 규격 적용
                    timestamp = data.get("timestamp", current_time)
                    x = data.get("x", 0.0)
                    y = data.get("y", 0.0)
                    strategy_id = data.get("strategy_id", "unknown")

                    refined = {
                        "timestamp": float(timestamp),
                        "x": float(x),
                        "y": float(y),
                        "strategy_id": str(strategy_id)
                    }

                    self.visual_buffer.append(refined)
                    self.last_send_time = current_time

                self.input_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception:  # noqa: BLE001
                # 🛡️ [예외 격리] 에러 발생 시 로그 기록 후 루프 복구
                await asyncio.sleep(0.01)

    def serialize_for_frontend(self) -> bytes:
        """[목표 B] Orjson을 활용한 시각화 데이터 패키징"""
        # 🛡️ [STANDBY_OVERRIDE 방어] 정지 신호 시 빈 상태값(Idle)을 송신
        if self.standby_mode:
            return orjson.dumps({"state": "IDLE"})
        return orjson.dumps(list(self.visual_buffer))
