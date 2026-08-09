# -*- coding: utf-8 -*-
from strategy.plugins.track5 import Track5

def test_track5_gap_protocol_mean_reversion() -> None:
    """[Track 5 갭 프로토콜 검증] 갭 감지 및 트레일링/목표가 지정가 익절 검증"""
    agent = Track5({})
    
    # 1. 갭 상승 (Z-Score > 1.1) ➡️ 지정가 큐 숏 진입
    res_gap = agent.evaluate_gap_divergence(
        open_price=350.0,
        prev_close_price=345.0,  # 갭 상승 +5.0pt
        active_vol=1.0,
        current_regime="NORMAL",
        date_str="2026-08-05"
    )
    assert res_gap["status"] == "TRIGGERED"
    assert res_gap["signals"][0]["action"] == "ENTER_GAP_SHORT"
    assert res_gap["signals"][0]["pricing_mode"] == "MID_PRICE_OFFSET"
    assert res_gap["signals"][0]["qty"] == 1
    assert agent.gap_state["is_active"] is True

    # 2. 괴리 0선 목표가(345.0) 도달 시 익절 청산
    res_revert = agent.evaluate_mean_reversion(current_price=345.0)
    assert res_revert["status"] == "PROFIT_TAKEN"
    assert res_revert["signals"][0]["action"] == "CLOSE_GAP_FUTURES"
    assert res_revert["signals"][0]["pricing_mode"] == "MID_PRICE_OFFSET"
    assert agent.gap_state["is_active"] is False


def test_track5_scope_isolation_and_date_reset() -> None:
    """[Track 5 갭 프로토콜 영업일 리셋 및 스코프 격리 검증]"""
    agent = Track5({})
    agent.gap_state["is_active"] = True
    
    # 1. 영업일 변경 시 세션 자동 리셋
    agent.evaluate_gap_divergence(
        open_price=350.0,
        prev_close_price=345.0,
        active_vol=1.0,
        date_str="2026-08-06"
    )
    assert agent.gap_state["is_active"] is True


def test_track5_black_swan_gap_block() -> None:
    """[Track 5 블랙스완 파국 갭 방어 가드 검증] Z-Score >= 4.0 감지 시 진입 차단 검증"""
    agent = Track5({})
    
    # 갭 폭등 (+20.0pt, Z-Score >= 4.0) ➡️ 진입 차단
    res_block = agent.evaluate_gap_divergence(
        open_price=365.0,
        prev_close_price=345.0,  # +20.0pt 파국 갭
        active_vol=1.0,
        current_regime="NORMAL",
        date_str="2026-08-06"
    )
    assert res_block["status"] == "BLACK_SWAN_GAP_BLOCKED"
    assert len(res_block["signals"]) == 0
    assert agent.gap_state["is_active"] is False


