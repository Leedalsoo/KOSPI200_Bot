import pytest
from strategy.plugins.track9 import Track9

def test_track9_default_90_percent_early_profit_take():
    """
    [PHASE 33 RED->GREEN VERIFICATION TEST]
    Track 9 오버나잇 헷지 기본 익절 비율 90% 검증:
    1. 10계약 보유 시 unwind_qty = 9계약 (int(10 * 0.90) = 9) 산출
    2. realized_early_gain = 9 * 150,000원 = 1,350,000원 정산
    3. Atomic Clear 후 1계약 (10 - 9 = 1) 잔존 보존
    """
    t9 = Track9()  # default config
    res = t9.evaluate_early_morning_profit_take(time_str="09:02:00", current_ins_qty=10)
    
    assert res["status"] == "EARLY_PROFIT_TAKE"
    assert len(res["signals"]) == 1
    
    sig = res["signals"][0]
    unwind_qty = sig["qty"]
    unwind_ratio = sig["unwind_ratio"]
    
    # 1. 9계약 (90%) 산출 검증
    assert unwind_ratio == 0.90, f"Expected ratio 0.90, got {unwind_ratio}"
    assert unwind_qty == 9, f"Expected 9 contracts for 90% of 10, got {unwind_qty}"
    
    # 2. 1,350,000원 이익금 정산 검증
    realized_early_gain = unwind_qty * 150000.0
    assert realized_early_gain == 1350000.0, f"Expected 1,350,000 KRW, got {realized_early_gain}"
    
    # 3. 잔존 수량 정합성 검증 (10 - 9 = 1)
    remaining_qty = 10 - unwind_qty
    assert remaining_qty == 1, f"Expected 1 remaining contract, got {remaining_qty}"
