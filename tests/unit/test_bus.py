import pytest
import asyncio
import time
from typing import Any
from core.bus import EventBus, EventPriority

@pytest.mark.asyncio
async def test_event_bus_priority_retrieval() -> None:
    """[목표 A 검증] 큐 정렬 순서 보장 (EXECUTION 우선)"""
    bus = EventBus()
    await bus.publish(EventPriority.TICK, "TICK", "tick_data", time.time())
    await bus.publish(EventPriority.EXECUTION, "EXEC", "exec_data", time.time())
    
    first_event = await bus._queue.get()
    assert first_event[2] == "EXEC"
    assert first_event[3] == "exec_data"

@pytest.mark.asyncio
async def test_event_bus_stale_data_drop() -> None:
    """[목표 B 검증] 200ms 초과 지연 데이터(Stale Data) Drop 로직 증명"""
    bus = EventBus()
    stale_time = time.time() - 0.3  # 300ms 과거
    await bus.publish(EventPriority.TICK, "TICK", "stale_data", stale_time)
    
    # process_events 루프를 1사이클만 돌려보기 위해 콜백이 호출되지 않음을 증명
    called = False
    async def dummy_callback(data: Any) -> None:
        nonlocal called
        called = True
        
    bus.subscribe("TICK", dummy_callback)
    
    task = asyncio.create_task(bus.process_events())
    
    # Allow event loop to process
    await asyncio.sleep(0.05)
    bus._running = False
    task.cancel()
    
    assert called is False, "Stale data should have been dropped, but callback was called"

@pytest.mark.asyncio
async def test_subscriber_exception_isolation() -> None:
    """[목표 B 검증] 특정 콜백 에러 시 버스 즉사 방지 (격리 증명)"""
    bus = EventBus()
    success_flag = False

    async def bad_callback(data: Any) -> None:
        raise ValueError("Simulated Callback Error")

    async def good_callback(data: Any) -> None:
        nonlocal success_flag
        success_flag = True

    bus.subscribe("TEST", bad_callback)
    bus.subscribe("TEST", good_callback)
    
    await bus.publish(EventPriority.SYSTEM, "TEST", "data", time.time())
    
    task = asyncio.create_task(bus.process_events())
    
    # Allow event loop to process
    await asyncio.sleep(0.05)
    bus._running = False
    task.cancel()
    
    assert success_flag is True, "Good callback should have executed despite bad callback raising an error"
