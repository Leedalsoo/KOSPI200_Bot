# -*- coding: utf-8 -*-
import pytest
from strategy.plugins.track7 import Track7

def test_track7_weekly_insurance_buy_and_take_profit() -> None:
    """[Track 7 위클리 보험 검증] 상장 첫날 지정가 분할 큐 매수 및 기술적 선제 지정가 익절 검증"""
    agent = Track7({})
    
    # 1. 상장 첫날 (is_new_week_start=True) ➡️ 지정가 분할 큐 매수
    res_buy = agent.evaluate_insurance_buy(
        current_price=350.0,
        budget=1000000.0,
        date_str="2026-08-05",
        is_new_week_start=True,
        active_vol=1.0,
        time_str="09:05:00"
    )
    assert res_buy["status"] == "TRIGGERED"
    assert res_buy["signals"][0]["action"] == "BUY_LIMIT_WEEKLY_INSURANCE"
    assert res_buy["signals"][0]["pricing_mode"] == "MID_PRICE_OFFSET"
    assert agent.insurance_state["is_active"] is True

    # 2. 2단계 하이브리드 트레일링 스탑 ➡️ 이익선 돌파 후 선제 지정가 예약 큐 방출 및 반락 익절
    res_tp1 = agent.evaluate_take_profit(current_price=385.0)  # 2.0배 돌파 -> 트레일링 스탑 ON 및 선제 지정가 예약 큐 생성
    assert agent.insurance_state["trailing_stop_active"] is True
    assert res_tp1["status"] == "TRAILING_STOP_LIMIT_QUEUE_UPDATED"
    assert res_tp1["signals"][0]["action"] == "TAKE_PROFIT_PREEMPTIVE_TRAILING_LIMIT"
    assert res_tp1["signals"][0]["limit_offset_ticks"] == 2
    
    res_tp2 = agent.evaluate_take_profit(current_price=370.0)  # 반락 -> 익절
    assert res_tp2["status"] == "PROFIT_TAKEN_TRAILING_STOP"
    assert res_tp2["signals"][0]["action"] == "TAKE_PROFIT_HYBRID_TRAILING_STOP"
    assert agent.insurance_state["is_active"] is False


def test_track7_skew_arbitrage_and_stop_loss() -> None:
    """[Track 7 Skew 차익거래 검증] IV Skew 괴리 1차 지정가 진입 및 왜곡 손절 검증"""
    agent = Track7({})
    
    # 1. Put IV 25.0 - Call IV 20.0 = Skew 5.0 >= 3.0 ➡️ 1차 지정가 예약 진입
    market_skew_enter = {
        "date_str": "2026-08-05",
        "call_iv": 20.0,
        "put_iv": 25.0
    }
    res_enter = agent.evaluate_skew_arbitrage(market_skew_enter)
    assert res_enter["status"] == "SKEW_LIMIT_PENDING"
    assert res_enter["signals"][0]["action"] == "ENTER_SKEW_ARB_LIMIT"
    assert res_enter["signals"][0]["qty"] == 1
    assert agent.skew_active is True

    # 2. Skew 왜곡 심화 (put_iv 30.0 - call_iv 20.0 = skew 10.0 > 8.0) ➡️ 손절
    market_skew_stop = {
        "date_str": "2026-08-05",
        "call_iv": 20.0,
        "put_iv": 30.0
    }
    res_stop = agent.evaluate_skew_arbitrage(market_skew_stop)
    assert res_stop["status"] == "SKEW_STOP_LOSS"
    assert res_stop["signals"][0]["action"] == "CLOSE_SKEW_ARB_STOP_LOSS"
    assert agent.skew_active is False


@pytest.mark.asyncio
async def test_track7_scope_isolation_and_date_reset() -> None:
    """[Track 7 스코프 격리 및 원자 예산/영업일 리셋 검증]"""
    agent = Track7({})
    
    res_async_buy = await agent.evaluate_insurance_buy_async(
        current_price=350.0,
        budget=1000000.0,
        date_str="2026-08-05",
        is_new_week_start=True
    )
    assert res_async_buy["status"] == "TRIGGERED"
    assert res_async_buy["signals"][0]["action"] == "BUY_LIMIT_WEEKLY_INSURANCE"

    agent.skew_active = True
    market_scoped = {
        "date_str": "2026-08-05",
        "call_iv": 20.0,
        "put_iv": 20.2,  # skew = 0.2 (정상 회귀 범위)
        "total_fees": 100000.0,
        "current_pnl": 200000.0,
        "track7_total_fees": 0.0,
        "track7_current_pnl": 0.0,
    }
    res_scope = agent.evaluate_skew_arbitrage(market_scoped)
    assert res_scope["status"] == "SKEW_CLOSED"
    assert res_scope["signals"][0]["action"] == "CLOSE_SKEW_ARB_LIMIT"
    assert agent.skew_active is False

    # 4. is_expiry_day 만기일 컷오프 검증 (금요일이 아닌 목요일 공휴일 전일 당겨진 만기일 대응)
    agent.insurance_state["is_active"] = True
    res_cutoff_limit = agent.evaluate_expiry_cutoff(time_str="15:00:00", is_expiry_day=True, date_str="2026-08-05")
    assert res_cutoff_limit["status"] == "CUTOFF_LIMIT_PENDING"
    assert res_cutoff_limit["signals"][0]["action"] == "CLOSE_WEEKLY_INSURANCE_LIMIT"

    res_cutoff_fallback = agent.evaluate_expiry_cutoff(time_str="15:16:00", is_expiry_day=True, date_str="2026-08-05")
    assert res_cutoff_fallback["status"] == "CUTOFF_FALLBACK_EXECUTED"
    assert res_cutoff_fallback["signals"][0]["action"] == "CLOSE_WEEKLY_INSURANCE_FALLBACK_MARKET"
    assert agent.insurance_state["is_active"] is False

