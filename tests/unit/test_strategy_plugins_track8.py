# -*- coding: utf-8 -*-
import pytest
from strategy.plugins.track8 import Track8

def test_track8_monthly_strangle_entry_and_cutoff() -> None:
    """[Track 8 월간 양매수 검증] 월물 초입 지정가 분할 큐 진입 및 D-4 만기 조건부 청산 검증"""
    agent = Track8({})
    
    # 1. DTE = 20.0 (월물 초입 >= 15.0), 예산 3,000,000 ➡️ 양매수 지정가 분할 큐 진입
    res_entry = agent.evaluate_entry(
        dte=20.0,
        budget=3000000.0,
        current_price=350.0,
        current_regime="NORMAL",
        date_str="2026-08-05"
    )
    assert res_entry["status"] == "TRIGGERED"
    assert res_entry["signals"][0]["action"] == "BUY_LIMIT_TRANCHE"
    assert res_entry["signals"][0]["pricing_mode"] == "MID_PRICE_OFFSET"
    assert res_entry["signals"][0]["qty"] == 1
    assert agent.strangle_state["is_active"] is True

    # 2. DTE = 3.5, 지수가 중앙에 갇혀 있음(OTM) ➡️ D-4 컷오프(Flat)
    res_cutoff = agent.evaluate_expiry_cutoff(
        dte=3.5,
        current_price=350.0,
        active_vol=1.0,
        time_str="10:00:00",
        date_str="2026-08-05"
    )
    assert res_cutoff["status"] == "CUTOFF_TRIGGERED"
    assert res_cutoff["signals"][0]["action"] == "FLAT_STRANGLE"
    assert agent.strangle_state["is_active"] is False


def test_track8_dynamic_hold_and_hysteresis_loop() -> None:
    """[Track 8 다이내믹 3중 루프 & 히스테리시스 필터 검증] Moneyness 밀접 시 홀딩 유예 검증"""
    agent = Track8({})
    
    # 1. 진입 세팅 (Call: 365.0, Put: 335.0)
    agent.evaluate_entry(dte=20.0, budget=3000000.0, current_price=350.0, current_regime="NORMAL", date_str="2026-08-05")
    
    # 2. DTE = 3.0 이지만 지수가 콜 행사가(365.0)의 ±3% 범위 내(360.0)로 접근 ➡️ DYNAMIC_HOLD_PRESERVED 유예
    res_dynamic = agent.evaluate_expiry_cutoff(
        dte=3.0,
        current_price=360.0,  # abs(360 - 365) / 365 = 1.37% <= 3%
        active_vol=1.0,
        time_str="09:05:00",
        date_str="2026-08-05"
    )
    assert res_dynamic["status"] == "DYNAMIC_HOLD_PRESERVED"
    assert res_dynamic["signals"][0]["action"] == "HOLD_LONG_ATTACK"
    assert agent.strangle_state["is_active"] is True

    # 3. 다음 순간 지수가 잠시 이탈하더라도 히스테리시스 필터가 작용 ➡️ HYSTERESIS_FILTER_ACTIVE
    res_hysteresis = agent.evaluate_expiry_cutoff(
        dte=2.5,
        current_price=350.0,  # 중간 박스권
        active_vol=1.0,
        time_str="13:30:00",
        date_str="2026-08-05"
    )
    assert res_hysteresis["status"] == "HYSTERESIS_FILTER_ACTIVE"
    assert agent.strangle_state["is_active"] is True


def test_track8_macro_regime_protection() -> None:
    """[Track 8 매크로 레짐 방어 검증] 고변동성/파국 위험 레짐 헷지 강화 시그널 검증"""
    agent = Track8({})
    
    market_data = {
        "date_str": "2026-08-05",
        "current_pnl": 0.0,
        "total_fees": 0.0
    }
    res_macro = agent.evaluate_macro_regime_protection(market_data, current_regime="HIGH_VOL")
    assert res_macro["status"] == "RISK_SCALE_UP"
    assert res_macro["signals"][0]["action"] == "MACRO_HEDGE_SCALE_UP"
    assert res_macro["signals"][0]["hedge_ratio_multiplier"] == 1.5


@pytest.mark.asyncio
async def test_track8_hybrid_trailing_stop() -> None:
    """[Track 8 2단계 하이브리드 트레일링 스탑 검증]"""
    agent = Track8({})
    agent.strangle_state["is_active"] = True
    agent.strangle_state["put_strike"] = 335.0
    agent.strangle_state["call_strike"] = 365.0
    agent.strangle_state["qty_call"] = 1
    agent.strangle_state["qty_put"] = 1
    agent.strangle_state["premium_spent"] = 500000.0

    # 1. 지수 390 (Call 대폭등 -> 평가액 6,250,000원 -> 2.5배 돌파 트레일링 스탑 ON 및 선제 지정가 예약 큐 생성)
    res_step1 = agent.evaluate_take_profit(current_price=390.0, active_vol=1.5)
    assert agent.strangle_state["trailing_stop_active"] is True
    assert res_step1["status"] == "TRAILING_STOP_LIMIT_QUEUE_UPDATED"
    assert res_step1["signals"][0]["action"] == "TAKE_PROFIT_PREEMPTIVE_TRAILING_LIMIT"
    assert res_step1["signals"][0]["limit_offset_ticks"] == 2

    # 2. 지수 375 (평가액 2,500,000원 -> 최고점 대비 15% 이상 반락 -> 트레일링 스탑 익절 집행)
    res_step2 = agent.evaluate_take_profit(current_price=375.0, active_vol=1.5)
    assert res_step2["status"] == "PROFIT_TAKEN_TRAILING_STOP"
    assert res_step2["signals"][0]["action"] == "TAKE_PROFIT_HYBRID_TRAILING_STOP"
    assert agent.strangle_state["is_active"] is False


@pytest.mark.asyncio
async def test_track8_scope_isolation_and_date_reset() -> None:
    """[Track 8 스코프 격리 및 원자 예산/영업일 리셋 검증]"""
    agent = Track8({})
    
    res_async_entry = await agent.evaluate_entry_async(
        dte=20.0,
        budget=3000000.0,
        current_price=350.0,
        current_regime="HIGH_VOL",
        date_str="2026-08-05"
    )
    assert res_async_entry["status"] == "TRIGGERED"
    assert res_async_entry["signals"][0]["action"] == "BUY_LIMIT_TRANCHE"
    assert agent.strangle_state["is_active"] is True

    market_scoped = {
        "date_str": "2026-08-05",
        "total_fees": 100000.0,
        "current_pnl": 200000.0,
        "track8_total_fees": 0.0,
        "track8_current_pnl": 0.0,
    }
    res_scope = agent.evaluate_macro_regime_protection(market_scoped, current_regime="NORMAL")
    assert res_scope["status"] == "HOLD"

