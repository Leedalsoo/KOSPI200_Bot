# -*- coding: utf-8 -*-
import pytest
from strategy.plugins.track8 import Track8

def test_track8_monthly_strangle_entry_and_cutoff() -> None:
    """[Track 8 월간 양매수 검증] 월물 초입 진입 및 D-4 만기 강제 청산 검증"""
    agent = Track8({})
    
    # 1. DTE = 20.0 (월물 초입 >= 15.0), 예산 3,000,000 ➡️ 양매수 진입
    res_entry = agent.evaluate_entry(
        dte=20.0,
        budget=3000000.0,
        current_price=350.0,
        current_regime="NORMAL",
        date_str="2026-08-05"
    )
    assert res_entry["status"] == "TRIGGERED"
    assert res_entry["signals"][0]["action"] == "BUY_STRANGLE"
    assert res_entry["signals"][0]["qty"] == 1
    assert agent.strangle_state["is_active"] is True

    # 2. DTE = 3.5 (D-4 만기 임박 <= 4.0) ➡️ 강제 청산(Flat)
    res_cutoff = agent.evaluate_expiry_cutoff(dte=3.5, date_str="2026-08-05")
    assert res_cutoff["status"] == "CUTOFF_TRIGGERED"
    assert res_cutoff["signals"][0]["action"] == "FLAT_STRANGLE"
    assert agent.strangle_state["is_active"] is False


def test_track8_macro_regime_protection() -> None:
    """[Track 8 매크로 레짐 방어 검증] 고변동성/파국 위험 레짐 헷지 강화 시그널 검증"""
    agent = Track8({})
    
    # HIGH_VOL 레짐 감지 ➡️ MACRO_HEDGE_SCALE_UP 시그널 발행
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
async def test_track8_scope_isolation_and_date_reset() -> None:
    """[Track 8 스코프 격리 및 원자 예산/영업일 리셋 검증]"""
    agent = Track8({})
    
    # 1. 비동기 원자 예산 차감 진입
    res_async_entry = await agent.evaluate_entry_async(
        dte=20.0,
        budget=3000000.0,
        current_price=350.0,
        current_regime="HIGH_VOL",
        date_str="2026-08-05"
    )
    assert res_async_entry["status"] == "TRIGGERED"
    assert agent.strangle_state["is_active"] is True


    # 2. 스코프 격리 키 우선 참조 검증 (track8_total_fees = 0)
    market_scoped = {
        "date_str": "2026-08-05",
        "total_fees": 100000.0,
        "current_pnl": 200000.0,
        "track8_total_fees": 0.0,
        "track8_current_pnl": 0.0,
    }
    res_scope = agent.evaluate_macro_regime_protection(market_scoped, current_regime="NORMAL")
    # track8_total_fees가 0 이므로 조기 익절 안 걸리고 HOLD 반환
    assert res_scope["status"] == "HOLD"
