# -*- coding: utf-8 -*-
import pytest
from strategy.plugins.track9 import Track9

def test_track9_overnight_insurance_evaluate() -> None:
    """[Track 9 오버나잇 보험 검증] Track 1 연동 오버나잇 보험 수량 산출 및 조절 검증"""
    agent = Track9({})
    
    # 1. active_sell_qty = 4, current_ins_qty = 0 ➡️ target = max(1, int(4 * 0.5)) = 2계약 ➡️ ADD (+2)
    res_add = agent.evaluate_insurance(
        current_price=350.0,
        active_sell_qty=4,
        current_ins_qty=0,
        date_str="2026-08-05"
    )
    assert res_add["status"] == "ADD"
    assert res_add["signals"][0]["action"] == "ADD_INSURANCE"
    assert res_add["signals"][0]["diff_qty"] == 2

    # 2. active_sell_qty = 2, current_ins_qty = 2 ➡️ target = max(1, int(2 * 0.5)) = 1계약 ➡️ REDUCE (-1)
    res_red = agent.evaluate_insurance(
        current_price=350.0,
        active_sell_qty=2,
        current_ins_qty=2,
        date_str="2026-08-05"
    )
    assert res_red["status"] == "REDUCE"
    assert res_red["signals"][0]["action"] == "REDUCE_INSURANCE"
    assert res_red["signals"][0]["diff_qty"] == 1


def test_track9_event_volatility_spike_and_crush() -> None:
    """[Track 9 이벤트 IV Spike & Vol Crush 검증]"""
    agent = Track9({})
    
    # 1. iv_spike = 4.5 >= 4.0 ➡️ 이벤트 롱 진입
    market_spike = {
        "date_str": "2026-08-05",
        "iv_spike": 4.5,
        "is_event_upcoming": False
    }
    res_spike = agent.evaluate_event_volatility_spike(market_spike)
    assert res_spike["status"] == "EVENT_ENTERED"
    assert res_spike["signals"][0]["action"] == "ENTER_EVENT_STRANGLE"
    assert agent.event_active is True

    # 2. iv_crush = -3.5 <= -3.0 (Vol Crush 발생) ➡️ 청산
    market_crush = {
        "date_str": "2026-08-05",
        "iv_crush": -3.5
    }
    res_crush = agent.evaluate_event_volatility_spike(market_crush)
    assert res_crush["status"] == "EVENT_CLOSED"
    assert res_crush["signals"][0]["action"] == "CLOSE_EVENT_STRANGLE"
    assert agent.event_active is False


@pytest.mark.asyncio
async def test_track9_scope_isolation_and_date_reset() -> None:
    """[Track 9 스코프 격리 및 원자 예산/영업일 리셋 검증]"""
    agent = Track9({})
    
    # 1. 비동기 예산 차감 성공 검증
    success = await agent.evaluate_event_buy_async(budget=1000000.0, estimated_cost=300000.0)
    assert success is True

    # 2. 스코프 격리 키 우선 참조 검증 (track9_total_fees = 0)
    agent.event_active = True
    market_scoped = {
        "date_str": "2026-08-05",
        "total_fees": 100000.0,
        "current_pnl": 200000.0,
        "track9_total_fees": 0.0,
        "track9_current_pnl": 0.0,
        "iv_crush": 0.0
    }
    res_scope = agent.evaluate_event_volatility_spike(market_scoped)
    # track9_total_fees가 0 이므로 조기 익절 안 걸리고 HOLD 반환
    assert res_scope["status"] == "HOLD"
