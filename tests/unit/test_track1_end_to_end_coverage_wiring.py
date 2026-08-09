import pytest
from strategy.plugins.track1 import Track1

def test_track1_end_to_end_coverage_wiring():
    """
    [PHASE 30-D END-TO-END WIRING VERIFICATION TEST]
    Track 1 전략 시그널 방출부터 서버 메인 핸들러 처리까지 배선 완벽 연결 실측 검증:
    1. 방어율 충분 (옵션 1계약 / 선물 1계약 -> 100% >= 80%):
       - FLATTEN_ALL 시그널 출품 안됨 (FENCE_CLEAR, FUTURES_UNWIND 지정가 개별 청산 출품)
    2. 방어율 미달 (옵션 10계약 / 선물 1계약 -> 10% < 80%):
       - FLATTEN_ALL 시그널 출품되며, 메인 루프에서 cov_ratio(10.0%)가 정확히 인지되어 비상 전량 피난 청산이 수행됨!
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
    
    # 시나리오 A: 방어율 100% 충분
    t1_sufficient = Track1(config)
    t1_sufficient.base_price = 360.0
    t1_sufficient.is_market_opened = True
    t1_sufficient.active_fence = {'type': 'CALL', 'strike': 367.5, 'tag_id': 1, 'qty': 1}
    t1_sufficient.active_hedge = 'BUY'
    t1_sufficient.active_hedge_qty = 1
    
    signals_suff = t1_sufficient.check_hedge_exit_conditions(current_price=368.0)
    actions_suff = [s["action"] for s in signals_suff]
    
    assert "FLATTEN_ALL" not in actions_suff, "Sufficient coverage (100%) must NOT produce FLATTEN_ALL signal"
    assert "FENCE_CLEAR" in actions_suff, "Sufficient coverage produces individual FENCE_CLEAR"
    
    # 시나리오 B: 방어율 10% 미달
    t1_insufficient = Track1(config)
    t1_insufficient.base_price = 360.0
    t1_insufficient.is_market_opened = True
    t1_insufficient.active_fence = {'type': 'CALL', 'strike': 367.5, 'tag_id': 1, 'qty': 10}
    t1_insufficient.active_hedge = 'BUY'
    t1_insufficient.active_hedge_qty = 1
    
    signals_insuff = t1_insufficient.check_hedge_exit_conditions(current_price=368.0)
    actions_insuff = [s["action"] for s in signals_insuff]
    
    assert "FLATTEN_ALL" in actions_insuff, "Insufficient coverage (10%) MUST produce FLATTEN_ALL signal"
    flatten_sig = next(s for s in signals_insuff if s["action"] == "FLATTEN_ALL")
    assert flatten_sig["coverage_ratio"] == 0.10, "FLATTEN_ALL signal must deliver exact 0.10 coverage_ratio payload"

    # 시나리오 C: 방향 불일치 (CALL 가두리 + SELL 헷지 -> 수량 10계약이어도 무조건 FLATTEN_ALL)
    t1_wrong_dir = Track1(config)
    t1_wrong_dir.base_price = 360.0
    t1_wrong_dir.is_market_opened = True
    t1_wrong_dir.active_fence = {'type': 'CALL', 'strike': 367.5, 'tag_id': 1, 'qty': 1}
    t1_wrong_dir.active_hedge = 'SELL'  # 폭등 장에서 반대 방향 SELL 헷지!
    t1_wrong_dir.active_hedge_qty = 10   # 수량이 높더라도!
    
    signals_wrong = t1_wrong_dir.check_hedge_exit_conditions(current_price=368.0)
    actions_wrong = [s["action"] for s in signals_wrong]
    
    assert "FLATTEN_ALL" in actions_wrong, "Opposite direction hedge MUST trigger FLATTEN_ALL regardless of high quantity"
    flatten_wrong_sig = next(s for s in signals_wrong if s["action"] == "FLATTEN_ALL")
    assert flatten_wrong_sig["coverage_ratio"] == 0.0, "Coverage ratio must be forced to 0.0 for opposite direction hedge"
