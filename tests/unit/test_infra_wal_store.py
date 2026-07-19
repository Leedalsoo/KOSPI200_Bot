# -*- coding: utf-8 -*-
import pytest
import os
import tempfile
import orjson
import asyncio
from decimal import Decimal
from uuid import uuid4
from datetime import datetime

from infra.wal_store import WalStore, wal_default

def test_wal_default_serialization() -> None:
    """[목표 B 검증] 커스텀 타입 직렬화 정합성 및 예외 차단 증명"""
    test_uuid = uuid4()
    test_dec = Decimal("350.55")
    test_dt = datetime.now()
    
    data = {"u": test_uuid, "d": test_dec, "t": test_dt}
    serialized = orjson.dumps(data, default=wal_default)
    
    parsed = orjson.loads(serialized)
    assert parsed["u"] == str(test_uuid)
    assert parsed["d"] == "350.55"

    # 🛡️ [직렬화 예외 차단 검증] 지원하지 않는 커스텀 객체 인입 시 TypeError 차단 증명
    class UnsupportedClass:
        pass

    with pytest.raises(TypeError):
        orjson.dumps({"unsupported": UnsupportedClass()}, default=wal_default)

@pytest.mark.asyncio
async def test_wal_store_save_and_load() -> None:
    """[목표 A 검증] 스레드풀 기반 비동기 I/O 동시 쓰기 시 순차성(Sequential FIFO) 스트레스 증명"""
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        log_path = tmp.name

    try:
        store = WalStore(log_path)
        
        # 🛡️ [동시성 순차성 스트레스 검증] 100개 요청을 일시에 병렬 전송
        # 단일 워커 ThreadPoolExecutor가 FIFO 방식으로 디스크에 정확히 순서대로 밀어 넣는지 입증
        tasks = [store.save_event("SEQ_TEST", {"seq": i}) for i in range(100)]
        await asyncio.gather(*tasks)
        
        history = await store.load_history()
        assert len(history) == 100
        
        # 0부터 99까지 한 치의 순서 오차도 없이 기록되었는지 단언
        for i, event in enumerate(history):
            assert event["event_type"] == "SEQ_TEST"
            assert event["data"]["seq"] == i

    finally:
        try:
            os.remove(log_path)
        except OSError:
            pass

@pytest.mark.asyncio
async def test_wal_store_corrupted_data_recovery() -> None:
    """[목표 C 검증] 정전 시나리오: 반쪽짜리 오염된 JSONL 줄이 있어도 정상 데이터는 파싱됨을 증명"""
    with tempfile.NamedTemporaryFile(delete=False, mode='wb') as tmp:
        # 정상 데이터 기록
        tmp.write(orjson.dumps({"event_type": "VALID", "data": 1}, option=orjson.OPT_APPEND_NEWLINE))
        # 오염된 반쪽 데이터 강제 주입
        tmp.write(b'{"event_type": "CORRUPTED", "da\n')
        # 정상 데이터 기록
        tmp.write(orjson.dumps({"event_type": "VALID2", "data": 2}, option=orjson.OPT_APPEND_NEWLINE))
        log_path = tmp.name

    try:
        store = WalStore(log_path)
        history = await store.load_history()
        # 크래시 없이 정상적인 2개의 라인만 복구되어야 함
        assert len(history) == 2
        assert history[0]["event_type"] == "VALID"
        assert history[1]["event_type"] == "VALID2"
    finally:
        try:
            os.remove(log_path)
        except OSError:
            pass
