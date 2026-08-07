# -*- coding: utf-8 -*-
import pytest
from decimal import Decimal
from datetime import datetime
import numpy as np
from uuid import uuid4

from core.contracts import ExecutionReport, OrderStatus
from strategy.plugins.track3 import Track3

def test_butterfly_legs_closed_wing_ratio() -> None:
    """[목표 A 검증] Butterfly 1:2:1 계약 비율 및 행사가 수학적 등간격 증명"""
    agent = Track3({})
    legs = agent._calculate_butterfly_legs(atm_strike=Decimal('350.0'), tick_size=Decimal('2.5'))
    
    assert len(legs) == 3
    # 1 ITM (Buy), 2 ATM (Sell), 1 OTM (Buy) 확인
    atm_leg = next(leg for leg in legs if leg['strike'] == Decimal('350.0'))
    assert atm_leg['qty'] == 2 and atm_leg['side'] == 'SELL'
    
    buy_legs = [leg for leg in legs if leg['side'] == 'BUY']
    assert sum(leg['qty'] for leg in buy_legs) == 2

    # 🛡️ [수학적 등간격 증명 보강] (ITM ~ ATM 간격 == ATM ~ OTM 간격)
    itm_leg = next(leg for leg in legs if leg['side'] == 'BUY' and leg['strike'] < Decimal('350.0'))
    otm_leg = next(leg for leg in legs if leg['side'] == 'BUY' and leg['strike'] > Decimal('350.0'))
    assert (Decimal('350.0') - itm_leg['strike']) == (otm_leg['strike'] - Decimal('350.0'))
    assert (Decimal('350.0') - itm_leg['strike']) == Decimal('2.5')

def test_calendar_iv_spread_numpy_validation() -> None:
    """[목표 B 검증] Numpy 기반 IV 스프레드 괴리 연산 무결성 증명 (양성/음성 및 에지 예외 완벽 입증)"""
    agent = Track3({})
    
    # 1. 양성 테스트: 최근 스프레드가 폭발적으로 벌어짐 (스프레드: -0.03 -> 0.05, 괴리: 0.0775 > 0.05 ➡️ True)
    near_iv_pos = np.array([0.15, 0.16, 0.15, 0.15, 0.25])
    far_iv_pos = np.array([0.18, 0.18, 0.18, 0.18, 0.20])
    assert agent._validate_calendar_spread_iv(near_iv_pos, far_iv_pos) is True

    # 2. 음성 테스트: 스프레드 격차가 매우 평온하고 균등함 (스프레드: -0.03 일치, 괴리: 0.0 <= 0.05 ➡️ False)
    near_iv_neg = np.array([0.15, 0.15, 0.15, 0.15, 0.15])
    far_iv_neg = np.array([0.18, 0.18, 0.18, 0.18, 0.18])
    assert agent._validate_calendar_spread_iv(near_iv_neg, far_iv_neg) is False

    # 3. 에지 케이스 예외 테스트: 배열 길이가 2 미만인 단일 요소 입력 시 False 처리 증명
    assert agent._validate_calendar_spread_iv(np.array([0.15]), np.array([0.18])) is False
    assert agent._validate_calendar_spread_iv(np.array([]), np.array([])) is False

@pytest.mark.asyncio
async def test_asymmetric_legging_sequence() -> None:
    """[목표 C 검증] OTM 체결 전까지 ATM 발주 금지 및 체결 후 ATM 즉각 발주 증명"""
    agent = Track3({})
    otm_spec = {"code": "OTM1", "price": Decimal('1.0'), "qty": 1, "side": "BUY"}
    atm_spec = {"code": "ATM1", "price": Decimal('3.0'), "qty": 1, "side": "SELL"}
    
    # 1. OTM 발주
    otm_order = await agent._execute_asymmetric_legging(otm_spec, atm_spec)
    assert otm_order.instrument_code == "OTM1"
    assert otm_order.client_order_id in agent.pending_legs
    
    # 2. 다른 주문 ID 체결 시 반응 없음 (무시)
    dummy_report = ExecutionReport(
        client_order_id=uuid4(),
        broker_order_id="1",
        fill_id="1",
        status=OrderStatus.FILLED,
        filled_qty=1,
        filled_price=Decimal("1.0"),
        remaining_qty=0,
        timestamp=datetime.now(),
        raw_response={}
    )
    assert await agent.on_leg_filled(dummy_report) is None
    
    # 3. 기다리던 OTM 체결 시 ATM 즉각 발주
    valid_report = ExecutionReport(
        client_order_id=otm_order.client_order_id,
        broker_order_id="2",
        fill_id="2",
        status=OrderStatus.FILLED,
        filled_qty=1,
        filled_price=Decimal("1.0"),
        remaining_qty=0,
        timestamp=datetime.now(),
        raw_response={}
    )
    atm_order = await agent.on_leg_filled(valid_report)
    assert atm_order is not None
    assert atm_order.instrument_code == "ATM1"
    assert otm_order.client_order_id not in agent.pending_legs # 상태 정리 검증


def test_track3_invalid_data_hold() -> None:
    """스프레드 데이터 부족(len < 10) 시 억울한 조기청산 없이 HOLD 상태 유지 검증"""
    agent = Track3({})
    
    # 1. 시계열 개수 부족 데이터 (len=5 < 10)
    res_short_data = agent.evaluate_arbitrage({"spread_history": [1.5]*5})
    assert res_short_data["status"] == "HOLD"
    assert len(res_short_data["signals"]) == 0
    
    # 2. 포지션 보유 중 데이터 부족 시 조기청산(CLOSE)되지 않고 HOLD 유지 검증
    agent.active_position = "SHORT_SPREAD"
    res_holding_short_data = agent.evaluate_arbitrage({"spread_history": [1.5]*5})
    assert res_holding_short_data["status"] == "HOLD"
    assert agent.active_position == "SHORT_SPREAD"
    assert len(res_holding_short_data["signals"]) == 0



def test_track3_stop_loss_and_timeout() -> None:
    """Z-Score 극단 이탈(|Z| >= 3.5) 손절 및 300틱 타임아웃 청산 검증"""
    agent = Track3({})
    agent.active_position = "SHORT_SPREAD"
    
    # 1. Z-Score = 4.0 (극단 이탈 -> 손절 STOP_LOSS)
    spread_history_stop = [0.0]*15 + [4.0]
    res_stop = agent.evaluate_arbitrage({"spread_history": spread_history_stop})
    assert res_stop["status"] == "STOP_LOSS"
    assert agent.active_position is None

    # 2. 타임아웃 검증 (300틱 도달)
    agent.active_position = "LONG_SPREAD"
    agent.holding_ticks = 299
    spread_history_normal = [0.0]*16  # z_score = 0.0 인 일반 상태
    res_timeout = agent.evaluate_arbitrage({"spread_history": spread_history_normal})
    assert res_timeout["status"] == "TIMEOUT_EXIT"
    assert agent.active_position is None


def test_track3_limit_queue_and_3stage_trailing_stop() -> None:
    """[Track 3 지정가 큐 및 3단계 동적 트레일링 스탑 검증]"""
    agent = Track3({})
    
    # 1. 진입 시 MID_PRICE_OFFSET 지정가 큐 방출 확인 (Z-Score = 2.0 >= 1.8)
    spread_history_enter = [0.0]*15 + [2.0]
    res_enter = agent.evaluate_arbitrage({"spread_history": spread_history_enter, "active_vol": 1.0, "base_vol": 1.0})
    assert res_enter["status"] == "ENTER_SHORT_SPREAD"
    assert res_enter["signals"][0]["pricing_mode"] == "MID_PRICE_OFFSET"
    assert res_enter["signals"][0]["limit_offset_ticks"] == 1
    assert agent.active_position == "SHORT_SPREAD"

    # 2. 3단계 동적 스케일링 트레일링 스탑 반락 락인 검증 (High Watermark 50만 원 ➡️ 44만 원 반락 -12%)
    # z_score가 1.0이 되도록 하여 평균 회귀 청산(<=0.2) 및 손절(>=3.5)을 모두 우회
    unclosed_spread = [0.0]*10 + [1.0]*6
    market_tp1 = {"spread_history": unclosed_spread, "track3_current_pnl": 500000.0, "premium_spent": 200000.0}
    agent.evaluate_arbitrage(market_tp1)
    
    market_tp2 = {"spread_history": unclosed_spread, "track3_current_pnl": 430000.0, "premium_spent": 200000.0}
    res_tp = agent.evaluate_arbitrage(market_tp2)
    assert res_tp["status"] == "TRAILING_PROFIT_LOCK"
    assert res_tp["signals"][0]["action"] == "CLOSE_STAT_ARB"
    assert res_tp["signals"][0]["pricing_mode"] == "PREEMPTIVE_STOP_LIMIT_QUEUE"
    assert agent.active_position is None

    # 3. 15:15 타임 가드 검증 (15:15:00 이후 신규 진입 차단)
    agent.active_position = None
    res_block = agent.evaluate_arbitrage({"spread_history": spread_history_enter, "active_vol": 1.0, "base_vol": 1.0, "time_str": "15:16:00"})
    assert res_block["status"] == "CLOSE_CUTOFF_BLOCK"
    assert len(res_block["signals"]) == 0

def test_track3_intraday_cutoff_forced_flatten() -> None:
    """15:15 장 마감 윈도우 진입 시 보유 중인 Track 3 포지션 100% 강제 Flat 및 신규 진입 차단 검증"""
    agent = Track3({})
    agent.active_position = "SHORT_SPREAD"
    agent.holding_ticks = 15
    
    # 1. 15:15:00 도달 시 MARKET_CLOSE_FLATTEN 및 CLOSE_STAT_ARB 시그널 방출 확인
    spread_normal = [0.0]*16
    res_flatten = agent.evaluate_arbitrage({"spread_history": spread_normal, "time_str": "15:15:00"})
    assert res_flatten["status"] == "MARKET_CLOSE_FLATTEN"
    assert len(res_flatten["signals"]) == 1
    assert res_flatten["signals"][0]["action"] == "CLOSE_STAT_ARB"
    assert res_flatten["signals"][0]["type"] == "CLOSE_SHORT_SPREAD"
    assert agent.active_position is None
    
    # 2. 15:15:10 다음 틱에서 멱등성 유지 (추가 청산 시그널 중복 방출 0건 및 CLOSE_CUTOFF_BLOCK 유지)
    res_next_tick = agent.evaluate_arbitrage({"spread_history": spread_normal, "time_str": "15:15:10"})
    assert res_next_tick["status"] == "CLOSE_CUTOFF_BLOCK"
    assert len(res_next_tick["signals"]) == 0
    assert agent.active_position is None

