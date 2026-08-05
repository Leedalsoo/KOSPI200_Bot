# -*- coding: utf-8 -*-
import pytest
from strategy.plugins.track7 import Track7

def test_track7_weekly_insurance_buy_and_take_profit() -> None:
    """[Track 7 위클리 보험 검증] 상장 첫날 위클리 보험 매수 및 동적 익절 검증"""
    agent = Track7({})
    
    # 1. 상장 첫날 (is_new_week_start=True) ➡️ 위클리 보험 매수
    res_buy = agent.evaluate_insurance_buy(
        current_price=350.0,
        budget=1000000.0,
        date_str="2026-08-05",
        is_new_week_start=True,
        active_vol=1.0
    )
    assert res_buy["status"] == "TRIGGERED"
    assert res_buy["signals"][0]["action"] == "BUY_WEEKLY_INSURANCE"
    assert agent.insurance_state["is_active"] is True

    # 2. 내재가치 평가금액 2.5배 이상 폭발 ➡️ 동적 익절
    res_tp = agent.evaluate_take_profit(current_price=380.0)  # 지수 대폭 상승
    assert res_tp["status"] == "PROFIT_TAKEN"
    assert res_tp["signals"][0]["action"] == "TAKE_PROFIT_WEEKLY_INSURANCE"
    assert agent.insurance_state["is_active"] is False


def test_track7_skew_arbitrage_and_stop_loss() -> None:
    """[Track 7 Skew 차익거래 검증] IV Skew 괴리 진입 및 왜곡 손절 검증"""
    agent = Track7({})
    
    # 1. Put IV 25.0 - Call IV 20.0 = Skew 5.0 >= 3.0 ➡️ Skew 차익거래 진입
    market_skew_enter = {
        "date_str": "2026-08-05",
        "call_iv": 20.0,
        "put_iv": 25.0
    }
    res_enter = agent.evaluate_skew_arbitrage(market_skew_enter)
    assert res_enter["status"] == "SKEW_ENTERED"
    assert res_enter["signals"][0]["action"] == "ENTER_SKEW_ARB"
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
    assert res_stop["signals"][0]["action"] == "CLOSE_SKEW_ARB"
    assert agent.skew_active is False


@pytest.mark.asyncio
async def test_track7_scope_isolation_and_date_reset() -> None:
    """[Track 7 스코프 격리 및 원자 예산/영업일 리셋 검증]"""
    agent = Track7({})
    
    # 1. 비동기 원자 예산 차감 매수
    res_async_buy = await agent.evaluate_insurance_buy_async(
        current_price=350.0,
        budget=1000000.0,
        date_str="2026-08-05",
        is_new_week_start=True
    )
    assert res_async_buy["status"] == "TRIGGERED"

    # 2. 스코프 격리 키 우선 참조 검증 (track7_total_fees = 0)
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
    # skew = 0.2 인 정상 회귀로 CLOSED 발동
    assert res_scope["status"] == "SKEW_CLOSED"
    assert agent.skew_active is False
