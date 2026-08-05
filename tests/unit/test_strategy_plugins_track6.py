# -*- coding: utf-8 -*-
import pytest
from strategy.plugins.track6 import Track6

def test_track6_volatility_spike_insurance_buy() -> None:
    """[Track 6 변동성 경보 검증] VKOSPI 1.3배 이상 폭발 시 0DTE 롱 스트랭글 매수 검증"""
    agent = Track6({})
    
    # 예산 500,000원, active_vol = 20.0 >= (15.0 * 1.3 = 19.5) ➡️ 매수 시그널 발동
    res_buy = agent.evaluate_insurance_buy(
        current_price=350.0,
        active_vol=20.0,
        base_vol=15.0,
        budget=500000.0,
        date_str="2026-08-05"
    )
    assert res_buy["status"] == "TRIGGERED"
    assert res_buy["signals"][0]["action"] == "BUY_DAILY_INSURANCE"
    assert res_buy["signals"][0]["qty"] == 1
    assert agent.insurance_state["is_active"] is True


def test_track6_mandatory_cutoff_at_1515() -> None:
    """[Track 6 만기 강제 청산 검증] 15:15:00 만기 강제 청산 철칙 검증"""
    agent = Track6({})
    agent.date_reset_helper.check_and_update("2026-08-05")  # 당일 세션 설정
    agent.insurance_state["is_active"] = True
    agent.insurance_state["long_put_strike"] = 337.5
    agent.insurance_state["long_call_strike"] = 362.5

    # 15:15:00 이전 (15:00:00) ➡️ HOLD
    res_hold = agent.evaluate_expiry_cutoff(time_str="15:00:00", date_str="2026-08-05")
    assert res_hold["status"] == "HOLD"
    assert agent.insurance_state["is_active"] is True

    # 15:15:00 도달 ➡️ CUTOFF_TRIGGERED
    res_cutoff = agent.evaluate_expiry_cutoff(time_str="15:15:00", date_str="2026-08-05")
    assert res_cutoff["status"] == "CUTOFF_TRIGGERED"
    assert res_cutoff["signals"][0]["action"] == "CLOSE_DAILY_INSURANCE"
    assert agent.insurance_state["is_active"] is False



@pytest.mark.asyncio
async def test_track6_atomic_budget_and_date_reset() -> None:
    """[Track 6 예산 부족 차단 & 원자 예산 차감 & 영업일 리셋 검증]"""
    agent = Track6({})
    
    # 1. 예산 부족 (예산 100,000 < 필요 예산 250,000) ➡️ NO_BUDGET
    res_nobudget = await agent.evaluate_insurance_buy_async(
        current_price=350.0,
        active_vol=20.0,
        base_vol=15.0,
        budget=100000.0,
        date_str="2026-08-05"
    )
    assert res_nobudget["status"] == "NO_BUDGET"

    # 2. 영업일 변경 시 세션 자동 리셋
    agent.insurance_state["is_active"] = True
    agent.evaluate_expiry_cutoff(time_str="10:00:00", date_str="2026-08-06")
    assert agent.insurance_state["is_active"] is False
