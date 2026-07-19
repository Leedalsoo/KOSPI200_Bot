# -*- coding: utf-8 -*-
import asyncio
import time
from typing import Any, Dict
import orjson
import pytest

from sensor.graph_strategy import GraphStrategyObserver


@pytest.mark.asyncio
async def test_sampling_rate() -> None:
    """[목표 A 검증] 1Hz 샘플링 속도 제어 동작 증명 (최소 1초 간격 유지)"""
    q: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
    observer = GraphStrategyObserver(q)
    await observer.start()

    try:
        # 고주파 데이터 연속 주입
        now = time.time()
        await q.put({"timestamp": now, "x": 350.0, "y": 10.0, "strategy_id": "track1"})
        await q.put({"timestamp": now + 0.1, "x": 350.1, "y": 11.0, "strategy_id": "track1"})
        await q.put({"timestamp": now + 0.2, "x": 350.2, "y": 12.0, "strategy_id": "track1"})

        # 큐 처리 비동기 대기
        await asyncio.sleep(0.05)

        # 1Hz 제한이므로 1개만 버퍼에 입력되어야 함
        assert len(observer.visual_buffer) == 1

        # 강제로 시간 경과 처리 후 주입
        observer.last_send_time = time.time() - 1.1
        await q.put({"timestamp": now + 1.2, "x": 350.3, "y": 13.0, "strategy_id": "track1"})
        
        await asyncio.sleep(0.05)
        
        # 간격이 경과되었으므로 두 번째 데이터가 추가됨
        assert len(observer.visual_buffer) == 2

    finally:
        await observer.stop()


@pytest.mark.asyncio
async def test_buffer_limit() -> None:
    """[목표 B 검증] deque의 maxlen=1000 제한이 메모리 안전성을 확보하는지 증명"""
    q: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
    observer = GraphStrategyObserver(q)
    # 테스트를 위한 샘플링 우회 활성화
    observer.bypass_sampling = True
    await observer.start()

    try:
        # 1005건의 데이터를 강제로 주입하되 샘플링 필터를 무력화하여 버퍼에 적재
        for i in range(1005):
            await q.put({"timestamp": float(i), "x": float(350 + i), "y": float(i), "strategy_id": "track1"})

        # 큐 처리 비동기 대기
        await asyncio.sleep(0.1)

        # deque maxlen=1000에 의해 1000개로 캡핑되어야 함
        assert len(observer.visual_buffer) == 1000

    finally:
        await observer.stop()


@pytest.mark.asyncio
async def test_orjson_serialization() -> None:
    """[목표 C 검증] 프론트엔드 규격 {timestamp, x, y, strategy_id}에 맞는 orjson 직렬화 확인"""
    q: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
    observer = GraphStrategyObserver(q)
    await observer.start()

    try:
        await q.put({"timestamp": 12345.67, "x": 350.5, "y": 15.5, "strategy_id": "track2"})
        await asyncio.sleep(0.05)

        raw_bytes = observer.serialize_for_frontend()
        parsed = orjson.loads(raw_bytes)

        # JSON 구조 검사
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        item = parsed[0]
        assert item["timestamp"] == 12345.67
        assert item["x"] == 350.5
        assert item["y"] == 15.5
        assert item["strategy_id"] == "track2"

    finally:
        await observer.stop()


@pytest.mark.asyncio
async def test_standby_idle_state() -> None:
    """[오라클 셧다운 검증] 정지 신호(standby_mode = True) 설정 시 IDLE 데이터 전송 및 버퍼 소거 증명"""
    q: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
    observer = GraphStrategyObserver(q)
    await observer.start()

    try:
        # 데이터 주입
        await q.put({"timestamp": 123.0, "x": 350.0, "y": 10.0, "strategy_id": "track1"})
        await asyncio.sleep(0.05)
        assert len(observer.visual_buffer) == 1

        # STANDBY_OVERRIDE 동기화
        observer.set_standby(True)

        # 버퍼가 즉각 클리어되어 비어있어야 함
        assert len(observer.visual_buffer) == 0

        # 직렬화 시 IDLE 상태 패킷을 송신해야 함
        raw_bytes = observer.serialize_for_frontend()
        parsed = orjson.loads(raw_bytes)
        assert parsed == {"state": "IDLE"}

        # 정지 신호 활성 상태에서 들어오는 신규 데이터 주입 시도
        await q.put({"timestamp": 124.0, "x": 350.0, "y": 10.0, "strategy_id": "track1"})
        await asyncio.sleep(0.05)

        # 버퍼에 여전히 쌓이지 않아야 함
        assert len(observer.visual_buffer) == 0

    finally:
        await observer.stop()
