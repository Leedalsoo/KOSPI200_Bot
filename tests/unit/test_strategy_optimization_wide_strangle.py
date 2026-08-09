# -*- coding: utf-8 -*-
import pytest
from strategy.plugins.track1 import Track1
from strategy.plugins.track8 import Track8
from strategy.plugins.track9 import Track9
from strategy.common import DynamicProfitRebuildEvaluator

def test_1_track1_wide_strangle_profit_take_and_rebuild():
    """TEST 1: Track 1 Wide Strangle 수익 발생 -> Profit Take -> 새로운 가두리 계산 재진입"""
    track1 = Track1({"strategies": {"strategy_1_1": {"params": {"profit_target": 300000.0}}}})
    track1.active_fence = {'type': 'PUT', 'strike': 340.0, 'tag_id': 1}
    
    # Gross PnL 600,000 -> Net PnL (마찰비용 차감 후) > 300,000
    res = track1.evaluate_dynamic_profit_rebuild(
        current_underlying=350.0,
        unrealized_pnl=600000.0,
        qty=1,
        tick_id="TICK_001"
    )
    
    assert res["status"] == "PROFIT_TAKEN_AND_REBUILT"
    assert len(res["signals"]) == 2
    assert res["signals"][0]["action"] == "DYNAMIC_PROFIT_TAKE"
    assert res["signals"][1]["action"] == "DYNAMIC_REBUILD_FENCE"
    assert res["signals"][1]["call_strike"] == 357.5
    assert res["signals"][1]["put_strike"] == 342.5

def test_2_track8_hedge_profit_take_and_rebuild():
    """TEST 2: Track 8 Hedge 수익 발생 -> Profit Take -> 헷지 공백 없이 새로운 Hedge 구축"""
    track8 = Track8({"profit_target": 250000.0})
    track8.strangle_state.update({
        "is_active": True,
        "call_strike": 365.0,
        "put_strike": 335.0
    })
    
    res = track8.evaluate_dynamic_profit_rebuild(
        current_price=350.0,
        unrealized_pnl=500000.0,
        qty=1,
        tick_id="TICK_002"
    )
    
    assert res["status"] == "PROFIT_TAKEN_AND_REBUILT"
    assert len(res["signals"]) == 2
    assert res["signals"][0]["action"] == "DYNAMIC_PROFIT_TAKE"
    assert res["signals"][1]["action"] == "DYNAMIC_REBUILD_FENCE"
    assert res["signals"][1]["call_strike"] == 365.0
    assert res["signals"][1]["put_strike"] == 335.0

def test_3_track9_overnight_gap_early_profit_take_and_rebuild():
    """TEST 3: Track 9 Overnight Gap -> 09:00 Gap 발생 -> Hedge PnL 급증 -> Profit Take -> Rebuild"""
    track9 = Track9({"profit_target": 300000.0})
    
    res = track9.evaluate_dynamic_profit_rebuild(
        current_price=352.5,
        unrealized_pnl=600000.0,
        time_str="09:02:00",
        qty=1,
        tick_id="TICK_003"
    )
    
    assert res["status"] == "PROFIT_TAKEN_AND_REBUILT"
    assert len(res["signals"]) == 2
    assert res["signals"][0]["action"] == "DYNAMIC_PROFIT_TAKE"
    assert res["signals"][0]["time_str"] == "09:02:00"
    assert res["signals"][1]["action"] == "DYNAMIC_REBUILD_FENCE"

def test_4_rapid_uptrend_rebuild_shift():
    """TEST 4: 급격한 상승 추세 -> 시장 재평가 -> 중심가격 상향 이동 가두리 재구축"""
    track1 = Track1({"strategies": {"strategy_1_1": {"params": {"profit_target": 200000.0}}}})
    
    # Underlying 급등: 350 -> 365
    res = track1.evaluate_dynamic_profit_rebuild(
        current_underlying=365.0,
        unrealized_pnl=500000.0,
        qty=1,
        tick_id="TICK_004"
    )
    
    assert res["status"] == "PROFIT_TAKEN_AND_REBUILT"
    rebuild_sig = res["signals"][1]
    # 중심가격 365 + 7.5 = 372.5, 365 - 7.5 = 357.5
    assert rebuild_sig["call_strike"] == 372.5
    assert rebuild_sig["put_strike"] == 357.5

def test_5_rapid_downtrend_rebuild_shift():
    """TEST 5: 급격한 하락 추세 -> 시장 재평가 -> 중심가격 하향 이동 가두리 재구축"""
    track1 = Track1({"strategies": {"strategy_1_1": {"params": {"profit_target": 200000.0}}}})
    
    # Underlying 급락: 350 -> 335
    res = track1.evaluate_dynamic_profit_rebuild(
        current_underlying=335.0,
        unrealized_pnl=500000.0,
        qty=1,
        tick_id="TICK_005"
    )
    
    assert res["status"] == "PROFIT_TAKEN_AND_REBUILT"
    rebuild_sig = res["signals"][1]
    # 중심가격 335 + 7.5 = 342.5, 335 - 7.5 = 327.5
    assert rebuild_sig["call_strike"] == 342.5
    assert rebuild_sig["put_strike"] == 327.5

def test_6_margin_diet_guard_blocks_rebuild():
    """TEST 6: Profit Take 직후 Risk Guard (MarginDietGuard) 발동 시 신규 Rebuild 차단"""
    track1 = Track1({"strategies": {"strategy_1_1": {"params": {"profit_target": 200000.0}}}})
    
    res = track1.evaluate_dynamic_profit_rebuild(
        current_underlying=350.0,
        unrealized_pnl=500000.0,
        qty=1,
        margin_ratio=0.90,  # 90% 증거금율 과다
        risk_guard_active=True,  # Risk Guard 발동
        tick_id="TICK_006"
    )
    
    assert res["status"] == "RISK_GUARD_BLOCKED"
    assert len(res["signals"]) == 0

def test_7_profit_target_not_met():
    """TEST 7: Profit Target 미달 시 Profit Take 및 Rebuild 미실행"""
    track1 = Track1({"strategies": {"strategy_1_1": {"params": {"profit_target": 500000.0}}}})
    
    # PnL 100,000 (목표 500,000 미달)
    res = track1.evaluate_dynamic_profit_rebuild(
        current_underlying=350.0,
        unrealized_pnl=100000.0,
        qty=1,
        tick_id="TICK_007"
    )
    
    assert res["status"] == "HOLD"
    assert len(res["signals"]) == 0

def test_8_fee_slippage_friction_rejects_profit_take():
    """TEST 8: Gross PnL은 존재하나 Fee + Slippage 고려 시 순이익(Net PnL) 부족으로 Profit Take 미실행"""
    evaluator = DynamicProfitRebuildEvaluator()
    
    # Gross 100,000원 -> 수수료+슬리피지 2회 왕복 차감 후 Net PnL 산출
    net_pnl = evaluator.calculate_expected_net_pnl(
        unrealized_pnl=100000.0,
        qty=2,
        estimated_slippage_ticks=2
    )
    
    # 마찰비용 차감으로 인해 Net PnL은 100,000원보다 훨씬 작아짐
    assert net_pnl < 100000.0
    
    triggered, _ = evaluator.evaluate_profit_take(
        unrealized_pnl=100000.0,
        qty=2,
        profit_target=90000.0
    )
    assert triggered is False

def test_9_idempotency_same_tick_duplicate_call_guard():
    """TEST 9: 동일 Tick 중복 호출 시 Idempotency 보장"""
    track1 = Track1({"strategies": {"strategy_1_1": {"params": {"profit_target": 200000.0}}}})
    
    # 1회차 호출: 정상 발동
    res1 = track1.evaluate_dynamic_profit_rebuild(
        current_underlying=350.0,
        unrealized_pnl=500000.0,
        qty=1,
        tick_id="TICK_SAME_001"
    )
    assert res1["status"] == "PROFIT_TAKEN_AND_REBUILT"
    
    # 동일 Tick_ID로 2회차 연속 호출: 중복 처리 방지
    res2 = track1.evaluate_dynamic_profit_rebuild(
        current_underlying=350.0,
        unrealized_pnl=500000.0,
        qty=1,
        tick_id="TICK_SAME_001"
    )
    assert res2["status"] == "HOLD"

def test_10_deterministic_replay_consistency():
    """TEST 10: 동일 Input 시 결정론적 (Deterministic) 결과 보장"""
    track9_a = Track9({"profit_target": 300000.0})
    track9_b = Track9({"profit_target": 300000.0})
    
    res_a = track9_a.evaluate_dynamic_profit_rebuild(
        current_price=350.0,
        unrealized_pnl=600000.0,
        time_str="09:01:00",
        qty=1,
        tick_id="TICK_REPLAY"
    )
    
    res_b = track9_b.evaluate_dynamic_profit_rebuild(
        current_price=350.0,
        unrealized_pnl=600000.0,
        time_str="09:01:00",
        qty=1,
        tick_id="TICK_REPLAY"
    )
    
    assert res_a["status"] == res_b["status"]
    assert res_a["signals"] == res_b["signals"]
    assert res_a["net_pnl"] == res_b["net_pnl"]
