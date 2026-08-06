# -*- coding: utf-8 -*-
import pytest
from strategy.plugins.track6 import Track6

def test_track6_volatility_spike_insurance_buy() -> None:
    """[Track 6 변동성 경보 검증] VKOSPI 1.3배 이상 폭발 시 Daily 0DTE HFT 지정가 큐 매수 검증"""
    agent = Track6({})
    
    # 예산 500,000원, active_vol = 20.0 >= (15.0 * 1.3 = 19.5) ➡️ 매수 시그널 발동
    res_buy = agent.evaluate_insurance_buy(
        current_price=350.0,
        active_vol=20.0,
        base_vol=15.0,
        budget=500000.0,
        date_str="2026-08-05",
        time_str="09:05:00"
    )
    assert res_buy["status"] == "TRIGGERED"
    assert res_buy["signals"][0]["action"] == "BUY_LIMIT_DAILY_INSURANCE"
    assert res_buy["signals"][0]["pricing_mode"] == "SUBSECOND_TICK_CHASER_IOC"
    assert res_buy["signals"][0]["qty"] == 1
    assert agent.insurance_state["is_active"] is True


def test_track6_mandatory_cutoff_at_1515() -> None:
    """[Track 6 만기 강제 청산 검증] 15:00 1단계 지정가 청산 & 15:15:00 2단계 예비 시장가 강제 청산 검증"""
    agent = Track6({})
    agent.date_reset_helper.check_and_update("2026-08-05")  # 당일 세션 설정
    agent.insurance_state["is_active"] = True
    agent.insurance_state["long_put_strike"] = 337.5
    agent.insurance_state["long_call_strike"] = 362.5

    # 15:00:00 ➡️ 1단계 지정가 선제 청산 (CUTOFF_LIMIT_PENDING)
    res_hold = agent.evaluate_expiry_cutoff(time_str="15:00:00", date_str="2026-08-05")
    assert res_hold["status"] == "CUTOFF_LIMIT_PENDING"
    assert res_hold["signals"][0]["action"] == "CLOSE_DAILY_INSURANCE_LIMIT"
    assert agent.insurance_state["is_active"] is True

    # 15:15:00 도달 ➡️ 2단계 예비 시장가 강제 청산 (CUTOFF_FALLBACK_EXECUTED)
    res_cutoff = agent.evaluate_expiry_cutoff(time_str="15:15:00", date_str="2026-08-05")
    assert res_cutoff["status"] == "CUTOFF_FALLBACK_EXECUTED"
    assert res_cutoff["signals"][0]["action"] == "CLOSE_DAILY_INSURANCE_FALLBACK_MARKET"
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


def test_track6_hybrid_trailing_stop() -> None:
    """[Track 6 2단계 하이브리드 트레일링 스탑 검증]"""
    agent = Track6({})
    agent.insurance_state["is_active"] = True
    agent.insurance_state["long_put_strike"] = 337.5
    agent.insurance_state["long_call_strike"] = 362.5
    agent.insurance_state["premium_spent"] = 250000.0

    # 1. 지수 380 (Call 대폭등 -> 평가액 4,375,000원 -> 1.5배 돌파 트레일링 스탑 ON 및 선제 지정가 예약 큐 방출)
    res_step1 = agent.evaluate_take_profit(current_price=380.0, active_vol=1.0, time_str="10:00:00")
    assert agent.insurance_state["trailing_stop_active"] is True
    assert res_step1["status"] == "TRAILING_STOP_LIMIT_QUEUE_UPDATED"
    assert res_step1["signals"][0]["action"] == "TAKE_PROFIT_PREEMPTIVE_TRAILING_LIMIT"
    assert res_step1["signals"][0]["limit_offset_ticks"] == 2

    # 1-2. 15:12:00 이후 ➡️ 트레일링 스탑 잠금 (LOCKDOWN_FOR_EXPIRY)
    res_lock = agent.evaluate_take_profit(current_price=380.0, active_vol=1.0, time_str="15:13:00")
    assert res_lock["status"] == "LOCKDOWN_FOR_EXPIRY"

    # 2. 지수 370 (평가액 1,875,000원 -> 최고점 대비 15% 이상 반락 -> 트레일링 스탑 익절 집행)
    res_step2 = agent.evaluate_take_profit(current_price=370.0, active_vol=1.0)
    assert res_step2["status"] == "PROFIT_TAKEN_TRAILING_STOP"
    assert res_step2["signals"][0]["action"] == "TAKE_PROFIT_HYBRID_TRAILING_STOP"
    assert agent.insurance_state["is_active"] is False


