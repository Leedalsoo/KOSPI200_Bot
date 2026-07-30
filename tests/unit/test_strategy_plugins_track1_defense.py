import pytest
from decimal import Decimal
from unittest.mock import AsyncMock
from typing import Dict, Any
from strategy.plugins.track1_defense import AdvancedDualSideDynamicStrangleStrategy

def test_kelly_and_mdd_shutdown() -> None:
    """[목표 A 검증] 1/8 Kelly 산출 정합성 및 MDD 셧다운 발동 증명"""
    ctx: Dict[str, Any] = {}
    agent = AdvancedDualSideDynamicStrangleStrategy(ctx)
    
    # Kelly
    fraction = agent._calculate_kelly_fraction(Decimal('0.6'), Decimal('1.5'))
    assert Decimal('0.041') < fraction < Decimal('0.042')
    
    # MDD (1000 -> 800: -20% 이므로 셧다운 True)
    assert agent._check_global_mdd_shutdown(Decimal('1000'), Decimal('800')) is True

@pytest.mark.asyncio
async def test_liquidity_discovery_protocol_sequence() -> None:
    """[목표 B 검증] 양날개 매수(BUY)가 본대 매도(SELL)보다 먼저 발주(리스트 앞단에 위치)되는지 증명"""
    ctx: Dict[str, Any] = {}
    agent = AdvancedDualSideDynamicStrangleStrategy(ctx)
    mock_risk = AsyncMock()
    mock_risk.validate.return_value = True # 마진 재검증 성공 모킹
    
    # 가상의 타겟 옵션 주입
    targets: Dict[str, Any] = {"wing": "OPT_WING", "body": "OPT_BODY"}
    orders = await agent._execute_liquidity_discovery(mock_risk, targets)
    
    # 날개(BUY) 주문이 리스트의 첫 번째, 본대(SELL)가 그 다음이어야 함
    assert len(orders) == 2
    assert orders[0].side == "BUY" and orders[0].instrument_code == "OPT_WING"
    assert orders[1].side == "SELL" and orders[1].instrument_code == "OPT_BODY"

def test_kill_switch_activation() -> None:
    """[목표 C 검증] 킬 스위치 발동 시 기존 포지션 청산(BUY TO COVER) 및 매수 스위칭 증명"""
    ctx: Dict[str, Any] = {}
    agent = AdvancedDualSideDynamicStrangleStrategy(ctx)
    # 극단적 감마/델타 위험 주입
    orders = agent._trigger_kill_switch({"Delta": Decimal('-50.0'), "Gamma": Decimal('-10.0')})
    # 청산 및 스위칭을 위한 여러 개의 지정가 주문이 생성되어야 함
    assert len(orders) > 0
    # 스위치를 위해 BUY 주문이 포함되어야 함
    assert any(o.side == "BUY" for o in orders)

def test_dynamic_futures_delta_hedging() -> None:
    """[목표 D 검증] 델타 데드밴드 버퍼 통제 및 선물 헤지 계약 수(반대 부호) 정합성 증명"""
    ctx: Dict[str, Any] = {}
    agent = AdvancedDualSideDynamicStrangleStrategy(ctx)
    
    # 1. 델타 +0.3 (Deadband 0.5 이내) -> 헤지 안 함 (0 계약)
    assert agent._calculate_futures_hedge_qty(Decimal('0.3')) == 0
    # 2. 델타 +1.8 (Deadband 초과) -> 매도(-) 2계약 필요
    assert agent._calculate_futures_hedge_qty(Decimal('1.8')) == -2
    # 3. 델타 -2.3 (Deadband 초과) -> 매수(+) 2계약 필요
    assert agent._calculate_futures_hedge_qty(Decimal('-2.3')) == 2
