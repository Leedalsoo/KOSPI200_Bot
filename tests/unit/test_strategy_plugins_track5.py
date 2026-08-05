# -*- coding: utf-8 -*-
from strategy.plugins.track5 import Track5

def test_track5_gap_protocol_mean_reversion() -> None:
    """[Track 5 갭 프로토콜 검증] 갭 감지 및 트레일링/목표가 익절 검증"""
    agent = Track5({})
    
    # 1. 갭 상승 (Z-Score > 1.1) ➡️ 숏 진입
    res_gap = agent.evaluate_gap_divergence(
        open_price=350.0,
        prev_close_price=345.0,  # 갭 상승 +5.0pt
        active_vol=1.0,
        current_regime="NORMAL",
        date_str="2026-08-05"
    )
    assert res_gap["status"] == "TRIGGERED"
    assert res_gap["signals"][0]["action"] == "ENTER_GAP_SHORT"
    assert res_gap["signals"][0]["qty"] == 1
    assert agent.gap_state["is_active"] is True

    # 2. 괴리 0선 목표가(345.0) 도달 시 익절 청산
    res_revert = agent.evaluate_mean_reversion(current_price=345.0)
    assert res_revert["status"] == "PROFIT_TAKEN"
    assert res_revert["signals"][0]["action"] == "CLOSE_GAP_FUTURES"
    assert agent.gap_state["is_active"] is False


def test_track5_atm_strangle_expiry_decay() -> None:
    """[Track 5 ATM 스트랭글 검증] DTE <= 1 세타 수취 빌드 및 IV 폭발 손절 검증"""
    agent = Track5({})
    
    # 1. 만기일 (DTE = 0.5 <= 1.0) ➡️ ATM 스트랭글 빌드
    market_data = {
        "date_str": "2026-08-05",
        "iv_spike": 1.0,
        "price_displacement": 0.5
    }
    res_build = agent.evaluate_atm_strangle_decay(market_data, days_to_expiry=0.5)
    assert res_build["status"] == "STRANGLE_BUILT"
    assert res_build["signals"][0]["action"] == "BUILD_ATM_STRANGLE"
    assert agent.strangle_active is True

    # 2. IV 폭발 (iv_spike = 6.0 > 5.0) ➡️ 스트랭글 손절
    market_data_spike = {
        "date_str": "2026-08-05",
        "iv_spike": 6.0,
        "price_displacement": 0.5
    }
    res_stop = agent.evaluate_atm_strangle_decay(market_data_spike, days_to_expiry=0.5)
    assert res_stop["status"] == "STRANGLE_STOP_LOSS"
    assert res_stop["signals"][0]["action"] == "CLOSE_ATM_STRANGLE"
    assert agent.strangle_active is False


def test_track5_scope_isolation_and_date_reset() -> None:
    """[Track 5 스코프 격리 및 영업일 리셋 검증]"""
    agent = Track5({})
    agent.strangle_active = True
    
    # 1. 영업일 변경 시 세션 자동 리셋
    market_new_date = {
        "date_str": "2026-08-06",
        "iv_spike": 1.0,
        "price_displacement": 0.0
    }
    agent.evaluate_atm_strangle_decay(market_new_date, days_to_expiry=2.0)
    assert agent.strangle_active is False  # 영업일 변경으로 리셋되어 False

    # 2. 스코프 격리 키 우선 참조 검증
    agent.strangle_active = True
    market_data_scoped = {
        "date_str": "2026-08-06",
        "total_fees": 100000.0,
        "current_pnl": 200000.0,
        "track5_total_fees": 0.0,
        "track5_current_pnl": 0.0,
    }
    res_scope = agent.evaluate_atm_strangle_decay(market_data_scoped, days_to_expiry=0.5)
    # track5_total_fees가 0 이므로 수수료 조기 익절 조건에 안 걸리고 HOLD 유지
    assert res_scope["status"] == "HOLD"
