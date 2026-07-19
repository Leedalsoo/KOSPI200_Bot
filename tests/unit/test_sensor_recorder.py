# -*- coding: utf-8 -*-
import pytest
import asyncio
import orjson
import os
import tempfile
from decimal import Decimal
from uuid import uuid4
from datetime import datetime

from core.bus import EventBus
from sensor.recorder import SensorRecorder

@pytest.mark.asyncio
async def test_recorder_zero_interference() -> None:
    """[목표 B 검증] 로깅이 비동기 큐로 즉시 넘어가고 메인 루프를 블로킹하지 않음을 증명"""
    bus = EventBus()
    recorder = SensorRecorder(bus, "test_telemetry.jsonl")
    
    start_time = asyncio.get_running_loop().time()
    # 1000개의 이벤트 동시 주입
    await asyncio.gather(*(recorder.on_event({"id": i}) for i in range(1000)))
    end_time = asyncio.get_running_loop().time()
    
    # 0.1초 내로 1000건이 큐에 적재되어야 함
    assert (end_time - start_time) < 0.1

    # 🛡️ [큐 오버플로우 드롭 정책 검증 보강]
    # 큐 크기를 10개로 아주 작게 모킹하여 15개 이벤트 주입 시 5개가 블로킹 없이 조용히 드롭되는지 검증
    small_recorder = SensorRecorder(bus, "small_telemetry.jsonl")
    small_recorder._queue = asyncio.Queue(maxsize=10)
    
    # 15개 이벤트 동시 주입 (QueueFull 상황 유도)
    for i in range(15):
        await small_recorder.on_event({"seq": i})
        
    # 예외나 락다운이 없이 큐 크기가 10개로 제한적으로 유지됨을 증명 (나머지 5개는 정상 드롭)
    assert small_recorder._queue.qsize() == 10

def test_orjson_serialization() -> None:
    """[목표 C 검증] 텔레메트리 데이터가 orjson으로 정상 직렬화 및 복원되는지 증명"""
    test_uuid = uuid4()
    test_dec = Decimal("100.25")
    test_dt = datetime.now()

    # orjson 직렬화 지원 확인을 위해 호환 타입 변환
    data = {
        "event_id": str(test_uuid),
        "price": str(test_dec),
        "timestamp": test_dt.isoformat()
    }
    
    serialized = orjson.dumps(data)
    parsed = orjson.loads(serialized)
    
    assert parsed["event_id"] == str(test_uuid)
    assert parsed["price"] == "100.25"
    assert parsed["timestamp"] == test_dt.isoformat()

@pytest.mark.asyncio
async def test_telemetry_file_round_trip() -> None:
    """[목표 C 검증] 임시 디스크 I/O 환경에서 bytes 적재 및 정상 복원(Round-trip) 입출력 무결성 증명"""
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        log_path = tmp.name

    try:
        bus = EventBus()
        recorder = SensorRecorder(bus, log_path)
        
        # 백그라운드 배치 리코더 가동
        await recorder.start()
        
        # 3개의 이벤트 주입
        await recorder.on_event({"event": "INIT", "val": 1.0})
        await recorder.on_event({"event": "PROCESS", "val": 2.0})
        await recorder.on_event({"event": "TERMINATE", "val": 3.0})
        
        # 배치 쓰기 태스크가 완료되도록 대기
        await asyncio.sleep(0.05)
        await recorder.stop()
        
        # 파일 내용을 바이너리(rb)로 다시 읽어 배치 적재 정합성 검증 (Round-trip)
        history = []
        with open(log_path, "rb") as f:
            for line in f:
                if line.strip():
                    history.append(orjson.loads(line))
                    
        assert len(history) == 3
        assert history[0]["event"] == "INIT"
        assert history[1]["event"] == "PROCESS"
        assert history[2]["event"] == "TERMINATE"
        
    finally:
        try:
            os.remove(log_path)
        except OSError:
            pass
