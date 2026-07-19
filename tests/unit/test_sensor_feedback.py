# -*- coding: utf-8 -*-
import pytest
from unittest.mock import AsyncMock

from core.bus import EventBus, EventPriority
from sensor.feedback import SensorFeedback

@pytest.mark.asyncio
async def test_emit_insight_lowest_priority() -> None:
    """[목표 A 검증] 전송된 Insight 메시지가 최하위 우선순위로 라우팅되는지 증명"""
    bus = AsyncMock(spec=EventBus)
    feedback = SensorFeedback(bus)
    
    await feedback.emit_insight("TRACK_1", 0.015, 2.5)
    
    # EventPriority.SYSTEM으로 호출되었는지 확인
    bus.publish.assert_called_once()
    args = bus.publish.call_args
    assert args[0][0] == EventPriority.SYSTEM  # 최하위 우선순위 검증
    
    # orjson 으로 직렬화 되었는지 payload 확인
    payload = args[0][2]
    assert "average_slippage" in payload
    assert payload["average_slippage"] == 0.015

@pytest.mark.asyncio
async def test_emit_insight_target_routing() -> None:
    """[목표 B 검증] 특정 전략 ID를 포함하는 이벤트 타입으로 라우팅됨을 증명"""
    bus = AsyncMock(spec=EventBus)
    feedback = SensorFeedback(bus)
    
    await feedback.emit_insight("TRACK_2", 0.008, 1.2)
    
    args = bus.publish.call_args
    event_type: str = args[0][1]
    payload = args[0][2]
    
    # 이벤트 타입에 타겟 전략 ID가 포함되어야 함
    assert "TRACK_2" in event_type
    
    # payload 봉투에도 타겟 ID가 명기되어야 함
    assert payload["target_strategy_id"] == "TRACK_2"
    assert payload["latency_ms"] == 1.2

@pytest.mark.asyncio
async def test_emit_insight_float_precision() -> None:
    """[목표 C 검증] float 반올림 처리 후 payload 정밀도 안전성 증명"""
    bus = AsyncMock(spec=EventBus)
    feedback = SensorFeedback(bus)

    # 6자리 이하 소수로 반올림 후 전달되는지 검증
    await feedback.emit_insight("TRACK_3", 0.0150001234567, 2.5999999)
    
    args = bus.publish.call_args
    payload = args[0][2]
    
    # round(..., 6) 처리 후 원본 float 미세오차를 소거함을 단언
    assert payload["average_slippage"] == round(0.0150001234567, 6)
    assert payload["latency_ms"] == round(2.5999999, 6)
