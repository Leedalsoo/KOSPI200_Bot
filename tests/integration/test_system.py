# -*- coding: utf-8 -*-
import asyncio
import pytest
from main import TradingSystem


@pytest.mark.asyncio
async def test_system_initialization_flow() -> None:
    """[목표 C 검증] 의존성 주입이 정상 작동하고 시스템이 초기화되는지 증명"""
    sys = TradingSystem({})
    await sys.initialize()
    assert sys.is_running is False  # 초기화 직후 running 상태


@pytest.mark.asyncio
async def test_graceful_shutdown_task_cancellation() -> None:
    """[목표 B 검증] Shutdown 시 태스크가 정상 취소되는지 증명"""
    sys = TradingSystem({})
    
    # 더미 백그라운드 태스크 하나 생성하여 루프에 돌림
    async def dummy_task() -> None:
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            raise

    task = asyncio.create_task(dummy_task())
    
    # shutdown 실행
    await sys.shutdown()
    
    # 생성한 더미 태스크가 정상적으로 취소(done) 처리되었음을 완증
    assert task.done()
    # 취소로 인해 정상 중단되었거나 취소 예외가 발생했는지 체크
    with pytest.raises((asyncio.CancelledError, Exception)):
        await task
