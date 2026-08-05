# -*- coding: utf-8 -*-
import pytest
import numpy as np
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Dict, Any
from uuid import uuid4
from core.contracts import MarketTick, OrderRequest
from infra.time_service import TimeService
from strategy.plugins.track2 import Track2

def test_market_trigger_bbw_and_zscore() -> None:
    """[원칙 1 검증] BBW 스퀴즈 및 거래량 Z-Score > 3.0 조건 결합 연산 무결성 증명"""
    ts = TimeService(mode="BACKTEST")
    ctx: Dict[str, Any] = {}
    agent = Track2(ctx, ts)
    
    # 거래량 폭발 배열 연출 (평균 10, 마지막 값 50 -> Z-Score > 3.0 조건 충족)
    vol_data = np.array([10.0]*19 + [50.0])
    # BBW 스퀴즈 상태 배열 (과거 대비 최저치 상태)
    bbw_data = np.array([0.05]*20) 
    
    assert agent._check_market_trigger(bbw_data, vol_data) is True

def test_market_trigger_bbw_and_zscore_boundary() -> None:
    """[경계값 검증] Z-Score 3.0 문턱값 전후(2.99 vs 3.01)에서의 정밀 사격 및 방아쇠 작동 증명"""
    ts = TimeService(mode="BACKTEST")
    ctx: Dict[str, Any] = {}
    agent = Track2(ctx, ts)
    bbw_data = np.array([0.05]*20)
    
    # 임의의 가상 거래량 데이터 이력
    history_vols = [8.0, 12.0] * 9 + [10.0]  # len=19.
    mean_vol = np.mean(history_vols)
    std_vol = np.std(history_vols)
    
    # 1. Z-Score = 2.99 가 되는 값 동적 계산 및 주입
    vol_data_low = np.array(history_vols + [mean_vol + 2.99 * std_vol])
    assert agent._check_market_trigger(bbw_data, vol_data_low) is False
    
    # 2. Z-Score = 3.01 이 되는 값 동적 계산 및 주입
    vol_data_high = np.array(history_vols + [mean_vol + 3.01 * std_vol])
    assert agent._check_market_trigger(bbw_data, vol_data_high) is True

def test_iv_skew_mismatch_abort() -> None:
    """[원칙 2 검증] IV 스큐 엇박자 발생 시 가짜 돌파(Whipsaw)로 인지하여 Abort(False)하는지 증명"""
    ts = TimeService(mode="BACKTEST")
    ctx: Dict[str, Any] = {}
    agent = Track2(ctx, ts)
    
    # OBI를 0.5 초과하게 만들기 위해 bid_qtys의 합을 더 크게 둠 (OBI = 0.66)
    tick = MarketTick("CODE", datetime.now(), Decimal("350.0"), 100, [Decimal("350.0")]*5, [Decimal("351.0")]*5, [10]*5, [2]*5)
    
    # 지수는 상방 돌파 신호(350.0 > 348.0)인데 풋 옵션 IV(near_iv = 0.4)가 콜 옵션 IV(far_iv = 0.2)보다 폭등하는 엇박자
    is_valid = agent._validate_whipsaw_filters(tick, basis=Decimal("0.5"), near_iv=Decimal("0.4"), far_iv=Decimal("0.2"), poc_price=Decimal("348.0"))
    
    # IV Skew 필터에 걸려 무조건 False가 나와야 함
    assert is_valid is False

def test_reversal_short_order_tick_quantization() -> None:
    """[원칙 3 검증] 스위칭 매도 주문 생성 시 옵션 틱 사이즈 테이블 연동 및 최소가격 클램핑 증명"""
    ts = TimeService(mode="BACKTEST")
    ctx: Dict[str, Any] = {}
    agent = Track2(ctx, ts)
    
    # 1. 3.0 미만 가격대: BBO 2.50 -> 2틱(0.02) 감산 -> 2.48
    long_order_1 = OrderRequest(uuid4(), uuid4(), "OPT_TRAP", Decimal("2.50"), 10, "BUY")
    reversal_1 = agent._generate_reversal_short_orders(long_order_1, Decimal("2.50"))
    assert reversal_1[0].price == Decimal("2.48")
    
    # 2. 3.0 이상 가격대: BBO 5.00 -> 2틱(0.10) 감산 -> 4.90
    long_order_2 = OrderRequest(uuid4(), uuid4(), "OPT_TRAP", Decimal("5.00"), 10, "BUY")
    reversal_2 = agent._generate_reversal_short_orders(long_order_2, Decimal("5.00"))
    assert reversal_2[0].price == Decimal("4.90")
    
    # 3. 극저가 가격대 클램핑: BBO 0.01 -> 2틱 감산 시 음수 또는 0 방어 -> 최소가격 0.01 클램핑
    long_order_3 = OrderRequest(uuid4(), uuid4(), "OPT_TRAP", Decimal("0.01"), 10, "BUY")
    reversal_3 = agent._generate_reversal_short_orders(long_order_3, Decimal("0.01"))
    assert reversal_3[0].price == Decimal("0.01")

@pytest.mark.asyncio
async def test_hardware_cooldown_timer_block() -> None:
    """[원칙 5 검증] 손절 발생 후 15분 하드웨어 쿨다운 시간 내 진입 시도 시 무조건 주문 차단 증명"""
    ts = TimeService(mode="BACKTEST")
    ctx: Dict[str, Any] = {}
    agent = Track2(ctx, ts)
    
    now = datetime(2026, 7, 17, 10, 0, 0)
    ts.set_virtual_time(now)
    
    # 손절 시간 기록 (현재 시각)
    agent._last_loss_time = now
    
    # 5분 지난 후(10시 5분) 기습 신호 도달 시나리오
    ts.set_virtual_time(datetime(2026, 7, 17, 10, 5, 0))
    
    # BBO 및 OBI > 0.5 충족
    tick = MarketTick("CODE", ts.get_current_time(), Decimal("350.0"), 10, [Decimal("350.0")]*5, [Decimal("351.0")]*5, [10]*5, [2]*5)
    bbw_data = np.array([0.05, 0.05, 0.04])
    vol_data = np.array([10.0]*5 + [50.0])
    
    orders = await agent.on_tick(tick, bbw_data, vol_data, Decimal("0.5"), Decimal("0.2"), Decimal("0.4"), Decimal("348.0"))
    
    # 15분이 안 지났으므로 방아쇠 조건을 모두 만족하더라도 무조건 빈 리스트 반환
    assert len(orders) == 0

@pytest.mark.asyncio
async def test_cooldown_release_and_daily_limit() -> None:
    """[원칙 5 검증] 15분 쿨다운 해제 시 정상 진입 및 일일 최대 2회 도달 시 3회째 기계적 차단 증명"""
    ts = TimeService(mode="BACKTEST")
    ctx: Dict[str, Any] = {}
    agent = Track2(ctx, ts)
    
    now = datetime(2026, 7, 17, 10, 0, 0)
    ts.set_virtual_time(now)
    
    # 1. 쿨다운 설정
    agent._last_loss_time = now
    
    # 2. 15분 1초 경과 시점(10시 15분 1초)에 틱 유입 -> 쿨다운 해제로 인해 진입 허용 확인
    ts.set_virtual_time(now + timedelta(minutes=15, seconds=1))
    
    tick = MarketTick("CODE", ts.get_current_time(), Decimal("350.0"), 10, [Decimal("350.0")]*5, [Decimal("351.0")]*5, [10]*5, [2]*5)
    bbw_data = np.array([0.05, 0.05, 0.04])
    vol_data = np.array([10.0]*5 + [50.0])
    
    orders1 = await agent.on_tick(tick, bbw_data, vol_data, Decimal("0.5"), Decimal("0.2"), Decimal("0.4"), Decimal("348.0"))
    assert len(orders1) == 1
    assert orders1[0].side == "BUY"
    assert agent._daily_entry_count == 1
    
    # 3. 2회차 진입 집행
    orders2 = await agent.on_tick(tick, bbw_data, vol_data, Decimal("0.5"), Decimal("0.2"), Decimal("0.4"), Decimal("348.0"))
    assert len(orders2) == 1
    assert agent._daily_entry_count == 2
    
    # 4. 3회차 진입 시도 -> 일일 2회 제한에 걸려 기계적으로 거부되어 [] 반환 확인
    orders3 = await agent.on_tick(tick, bbw_data, vol_data, Decimal("0.5"), Decimal("0.2"), Decimal("0.4"), Decimal("348.0"))
    assert len(orders3) == 0
