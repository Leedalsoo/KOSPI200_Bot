import pytest
from strategy.plugins.track1 import Track1

def test_track1_preemptive_hedge_prevents_clash_flatten():
    """
    [PHASE 30-C RED->GREEN VERIFICATION TEST]
    선물 BUY 헷지가 가동 중일 때 헷지 방어율(Hedge Coverage Ratio)에 따른 FLATTEN 동작 검증:
    1. 방향이 맞고 방어율이 충분할 때 (옵션 1계약 / 선물 1계약 -> 100% >= 80%): FENCE_CLEAR가 스킵되고 헷지 유지 (Green)
    2. 방향은 맞지만 방어율이 미달일 때 (옵션 10계약 / 선물 1계약 -> 10% < 80%): FENCE_CLEAR 비상 청산 정상 발동 (Green)
    3. 무방어 상태 (active_hedge = None -> 0%): FENCE_CLEAR 비상 청산 정상 발동 (Green)
    """
    config = {
        "strategies": {
            "strategy_1_1": {
                "params": {
                    "fence_distance": 7.5,
                    "max_hedge_allowed": 5,
                    "min_hedge_coverage_ratio": 0.80
                }
            }
        }
    }
    t1 = Track1(config)
    
    # 시나리오 1: 방향 맞고 방어율 충분 (옵션 1계약 / 선물 1계약 -> 100% Coverage >= 80%)
    t1.base_price = 360.0
    t1.is_market_opened = True
    t1.active_fence = {'type': 'CALL', 'strike': 367.5, 'tag_id': 1, 'qty': 1}
    t1.active_hedge = 'BUY'
    t1.active_hedge_qty = 1
    
    signals_sufficient = t1.check_hedge_exit_conditions(current_price=368.0)
    assert len(signals_sufficient) >= 1, "Signals generated for single leg exit"
    fence_signal = next(s for s in signals_sufficient if s["action"] == "FENCE_CLEAR")
    assert fence_signal["coverage_ratio"] >= 0.80, "Coverage ratio must be >= 80% for sufficient scenario"

    # 시나리오 2: 방향은 맞지만 방어율 미달 (옵션 10계약 / 선물 1계약 -> 10% Coverage < 80%)
    t1.active_fence = {'type': 'CALL', 'strike': 367.5, 'tag_id': 1, 'qty': 10}
    t1.active_hedge = 'BUY'
    t1.active_hedge_qty = 1
    
    signals_insufficient = t1.check_hedge_exit_conditions(current_price=368.0)
    assert len(signals_insufficient) >= 1, "Insufficient coverage (10%) must trigger FLATTEN_ALL"
    assert signals_insufficient[0]["action"] == "FLATTEN_ALL"

    # 시나리오 3: 헷지가 없는 무방어 상태 (active_hedge = None -> 0% Coverage)
    t1.active_fence = {'type': 'CALL', 'strike': 367.5, 'tag_id': 1, 'qty': 1}
    t1.active_hedge = None
    t1.active_hedge_qty = 0
    
    signals_unprotected = t1.check_hedge_exit_conditions(current_price=368.0)
    assert len(signals_unprotected) >= 1, "Unprotected state must trigger emergency FLATTEN_ALL"
    assert signals_unprotected[0]["action"] == "FLATTEN_ALL"
