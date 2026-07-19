# -*- coding: utf-8 -*-
import pytest
from decimal import Decimal
from datetime import datetime
import numpy as np
from uuid import uuid4

from core.contracts import ExecutionReport, OrderStatus
from strategy.plugins.track3_arbitrage import Track3Arbitrage

def test_butterfly_legs_closed_wing_ratio() -> None:
    """[목표 A 검증] Butterfly 1:2:1 계약 비율 및 행사가 수학적 등간격 증명"""
    agent = Track3Arbitrage({})
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
    agent = Track3Arbitrage({})
    
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
    agent = Track3Arbitrage({})
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
