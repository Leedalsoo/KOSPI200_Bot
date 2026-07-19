# -*- coding: utf-8 -*-
import pytest
import numpy as np
import asyncio
import time
from typing import Dict, Any
from strategy.regime_detector import RegimeDetector

def test_hmm_vectorization() -> None:
    """[목표 B 검증] numpy 연산이 루프 없이 고속으로 수행되는지 검증"""
    detector = RegimeDetector()
    
    # BULL 국면에 적합한 가상 데이터 생성 (평균 0.005 근처)
    bull_data = np.random.normal(0.005, 0.001, 1000)
    
    # 런타임 측정 및 루프 없이 고속 계산 확인
    start_time = time.perf_counter()
    loop = asyncio.new_event_loop()
    try:
        regime, _ = loop.run_until_complete(detector.detect_regime(bull_data))
    finally:
        loop.close()
    duration = time.perf_counter() - start_time
    
    # 1. 1000개의 데이터 연산이 0.05초 이내에 완료되어 벡터화가 작동 중인지 검증
    assert duration < 0.05
    # 2. 올바른 국면 검출 확인 (BULL)
    assert regime == "BULL"

def test_future_reference_check() -> None:
    """[목표 C 검증] 타임스탬프 미래 참조 방지 및 엠바고 로직 검증"""
    ctx: Dict[str, Any] = {}
    detector = RegimeDetector(ctx)
    
    # 1. 틱 연산 수행
    bull_data = np.array([0.005, 0.006, 0.004])
    loop = asyncio.new_event_loop()
    try:
        _, ts = loop.run_until_complete(detector.detect_regime(bull_data))
    finally:
        loop.close()
        
    now = time.time_ns()
    
    # 2. 반환 타임스탬프가 미래 시점을 가리키지 않는지 증명
    assert ts <= now
    
    # 3. 엠바고 시간(1초) 이전 가상 시간 주입 시 NEUTRAL 반환 확인 (미래 참조 방지)
    info = detector.get_regime_info(current_time_ns=ts + 500_000_000) # 0.5초 경과 시점
    assert info["regime"] == "NEUTRAL"
    assert info["embargo_active"] is True
    
    # 4. 엠바고 시간(1초) 이후 가상 시간 주입 시 정상 국면 반환 확인
    info_after = detector.get_regime_info(current_time_ns=ts + 1_500_000_000) # 1.5초 경과 시점
    assert info_after["regime"] == "BULL"
    assert info_after["embargo_active"] is False

@pytest.mark.asyncio
async def test_regime_broadcast() -> None:
    """[목표 D 검증] 국면 전환 시 비동기 이벤트 브로드캐스트 전파 증명"""
    detector = RegimeDetector()
    
    # 1. 비동기 대기 태스크 생성
    async def wait_regime_event() -> str:
        await detector._regime_event.wait()
        return detector.current_regime

    task = asyncio.create_task(wait_regime_event())
    
    # 2. 국면 강제 전환 유도 (SIDEWAYS 데이터 주입)
    sideways_data = np.array([0.000, 0.0001, -0.0001])
    await detector.detect_regime(sideways_data)
    
    # 3. 이벤트 대기 태스크가 깨어나서 정상 수신했는지 확인
    triggered_regime = await asyncio.wait_for(task, timeout=1.0)
    assert triggered_regime == "SIDEWAYS"

def test_standby_override() -> None:
    """[목표 E 검증] 오라클 모드(STANDBY_OVERRIDE) 진입 시 즉시 중립 상태로 전환 및 탐지 중단 증명"""
    ctx: Dict[str, Any] = {"standby_override": True}
    detector = RegimeDetector(ctx)
    
    # 강한 BULL 데이터 유입
    bull_data = np.array([0.005, 0.006, 0.004])
    loop = asyncio.new_event_loop()
    try:
        regime, _ = loop.run_until_complete(detector.detect_regime(bull_data))
    finally:
        loop.close()
        
    # 1. 오라클 오버라이드로 인해 강한 BULL 시그널에도 불구하고 NEUTRAL 유지 확인
    assert regime == "NEUTRAL"
    assert detector.current_regime == "NEUTRAL"
