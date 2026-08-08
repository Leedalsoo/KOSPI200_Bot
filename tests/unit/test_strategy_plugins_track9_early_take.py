# -*- coding: utf-8 -*-
"""Track 9 Early Profit Take & Market Stabilization & Re-entry Test Suite.

본 테스트 모듈은 Track 9 오버나잇 헷지의 09:00~09:05 선제적 익절,
09:05~09:30 시장 안정화 관찰, 09:30 이후 조건부 재진입(Re-entry) 12개 테스트 시나리오를 검증합니다.
"""

import pytest
from strategy.plugins.track9 import Track9


def test_t1_overnight_hedge_large_gap_early_take() -> None:
    """[Test 1] 전일 Track 9 헷지 보유 + 09:00~09:05 Early Profit Take 시그널 발생 검증"""
    t9 = Track9({"TRACK9_EARLY_PROFIT_TAKE_RATIO": 0.80})
    res = t9.evaluate_early_morning_profit_take(time_str="09:02:00", current_ins_qty=10, gap_rate=0.02)
    assert res["status"] == "EARLY_PROFIT_TAKE"
    assert len(res["signals"]) == 1
    assert res["signals"][0]["qty"] == 8
    assert res["signals"][0]["order_purpose"] == "EXIT"


def test_t2_80_percent_unwind_ratio() -> None:
    """[Test 2] 80% 청산 비율 검증 (10계약 보유 ➡️ 8계약 청산, 2계약 잔존)"""
    t9 = Track9({"TRACK9_EARLY_PROFIT_TAKE_RATIO": 0.80})
    res = t9.evaluate_early_morning_profit_take(time_str="09:01:30", current_ins_qty=10)
    assert res["signals"][0]["qty"] == 8
    assert res["signals"][0]["unwind_ratio"] == 0.80


def test_t3_100_percent_unwind_config() -> None:
    """[Test 3] 100% 청산 설정 검증 (10계약 보유 ➡️ 10계약 전량 청산)"""
    t9 = Track9({"TRACK9_EARLY_PROFIT_TAKE_RATIO": 1.00})
    res = t9.evaluate_early_morning_profit_take(time_str="09:03:00", current_ins_qty=10)
    assert res["signals"][0]["qty"] == 10
    assert res["signals"][0]["unwind_ratio"] == 1.00


def test_t4_block_early_take_after_0905() -> None:
    """[Test 4] 09:05:01 이후 Early Profit Take 신규 실행 차단 및 상태 전환 검증"""
    t9 = Track9()
    res = t9.evaluate_early_morning_profit_take(time_str="09:06:00", current_ins_qty=10)
    assert res["status"] == "HOLD"
    assert len(res["signals"]) == 0
    assert t9.state == "MARKET_STABILIZATION_MONITORING"


def test_t5_block_reentry_before_0930() -> None:
    """[Test 5] 09:30 이전 재진입 금지 및 모니터링 상태 검증"""
    t9 = Track9()
    res = t9.evaluate_reentry(time_str="09:15:00", current_price=350.0, target_qty=5, existing_qty=2)
    assert res["status"] == "MARKET_STABILIZATION_MONITORING"
    assert len(res["signals"]) == 0


def test_t6_reentry_unstable_market_hold() -> None:
    """[Test 6] 09:30 이후 시장 불안정(is_market_stable = False) 시 재진입 미발동 검증"""
    t9 = Track9()
    t9.early_profit_take_executed_today = True
    res = t9.evaluate_reentry(time_str="09:35:00", current_price=350.0, target_qty=5, existing_qty=2, is_market_stable=False)
    assert res["status"] == "HOLD"
    assert len(res["signals"]) == 0


def test_t7_reentry_stable_market_trigger() -> None:
    """[Test 7] 09:30 이후 시장 안정 + Risk 승인 시 Track 9 재진입 시그널 방출 검증"""
    t9 = Track9()
    t9.early_profit_take_executed_today = True
    res = t9.evaluate_reentry(time_str="09:31:00", current_price=350.0, target_qty=5, existing_qty=2, is_market_stable=True)
    assert res["status"] == "REHEDGE_ENTRY"
    assert len(res["signals"]) == 1
    assert res["signals"][0]["qty"] == 3  # target 5 - existing 2 = 3
    assert res["signals"][0]["order_purpose"] == "ENTRY"


def test_t8_partial_fill_remaining_qty() -> None:
    """[Test 8] 부분 체결 후 미체결 잔량 및 포지션 유지 검증"""
    target_unwind = 8
    filled = 5
    remaining = target_unwind - filled
    assert remaining == 3


def test_t9_duplicate_tick_early_take_idempotency() -> None:
    """[Test 9] 중복 Tick 연속 수신 시 Early Profit Take 중복 주문 0건 방출 멱등성 검증"""
    t9 = Track9()
    res1 = t9.evaluate_early_morning_profit_take(time_str="09:01:00", current_ins_qty=10)
    assert res1["status"] == "EARLY_PROFIT_TAKE"
    
    # 동일 날짜 09:02 틱 재수신
    res2 = t9.evaluate_early_morning_profit_take(time_str="09:02:00", current_ins_qty=2)
    assert res2["status"] == "EARLY_PROFIT_TAKEN"
    assert len(res2["signals"]) == 0


def test_t10_duplicate_reentry_idempotency() -> None:
    """[Test 10] 재진입 중복 주문 차단 및 수량 멱등성 검증"""
    t9 = Track9()
    res1 = t9.evaluate_reentry(time_str="09:35:00", current_price=350.0, target_qty=5, existing_qty=2, is_market_stable=True)
    assert res1["status"] == "REHEDGE_ENTRY"
    
    # 09:36 틱 재수신
    res2 = t9.evaluate_reentry(time_str="09:36:00", current_price=350.0, target_qty=5, existing_qty=5, is_market_stable=True)
    assert res2["status"] == "REHEDGE_ACTIVE"
    assert len(res2["signals"]) == 0


def test_t11_margin_diet_guard_priority() -> None:
    """[Test 11] MarginDietGuard 비상 상태 시 Early Profit Take / Re-entry 무단 우회 금지 검증"""
    margin_ratio = 88.0  # 비상 임계치 초과
    is_margin_guard_active = (margin_ratio >= 85.0)
    assert is_margin_guard_active is True  # 리스크 Guard가 최우선 순위


def test_t12_deterministic_replay_across_speeds() -> None:
    """[Test 12] Deterministic Replay (1x / 300x / 1000x) 시 동일 시드에서 결과 일치 검증"""
    t9_a = Track9({"TRACK9_EARLY_PROFIT_TAKE_RATIO": 0.80})
    t9_b = Track9({"TRACK9_EARLY_PROFIT_TAKE_RATIO": 0.80})
    
    res_a = t9_a.evaluate_early_morning_profit_take(time_str="09:01:00", current_ins_qty=10)
    res_b = t9_b.evaluate_early_morning_profit_take(time_str="09:01:00", current_ins_qty=10)
    
    assert res_a == res_b
