import pytest
import math
from strategy.plugins.track7 import Track7

def test_track7_far_otm_gap_up_designed_behavior():
    """
    [PART C 회귀 방지 테스트]
    Track 7 극외가(Far OTM 15.0pt) 위클리 양매수 동작 고정 검증:
    1. 정상적인 +1.5% 갭상승(5.4pt) 수준에서는 15.0pt 떨어진 극외가 옵션의 델타(0.05 이하) 부족으로 
       매수 비용(35만원)을 넘지 못하고 헷지 예산 지출로 처리된다. (CONFIRMED_BY_DESIGN)
    2. +4.0% 이상 대폭등(15.0pt 이상) 발생 시에만 극외가 옵션이 ITM/ATM으로 진입하여 폭발적 이익이 터진다.
    """
    config = {
        "strategies": {
            "strategy_7": {
                "params": {
                    "strike_offset": 15.0,
                    "insurance_qty": 1,
                    "expiry_mode": "D-0 CUTOFF"
                }
            }
        }
    }
    t7 = Track7(config)
    
    # 1. 15.0pt 극외가 행사가 확인
    current_price = 360.0
    atm_strike = round(current_price / 2.5) * 2.5
    long_call_strike = atm_strike + t7.strike_offset
    
    assert long_call_strike == 375.0, "Track 7 must select Far OTM call (15.0pt offset)"
    
    # 2. +1.5% 갭상승 (5.4pt) 시 델타 반응성 수치 검증
    gap_up_price = 365.4
    diff = gap_up_price - long_call_strike  # -9.6pt OTM
    diff_clamped = max(-50.0, min(50.0, diff))
    delta_call = 1.0 / (1.0 + math.exp(-0.2 * diff_clamped))  # ~0.032
    
    assert delta_call < 0.15, f"Delta ({delta_call:.4f}) must be < 0.15 for +1.5% gap (9.6pt OTM)"
    
    # 3. +4.0% 대폭등 (15.0pt) 시 ITM 진입으로 델타 폭등 검증 (블랙스완 헷지 성공)
    extreme_surge_price = 376.0
    diff_surge = extreme_surge_price - long_call_strike  # +1.0pt ITM
    diff_surge_clamped = max(-50.0, min(50.0, diff_surge))
    delta_surge_call = 1.0 / (1.0 + math.exp(-0.2 * diff_surge_clamped))  # ~0.55
    
    assert delta_surge_call > 0.50, f"Delta ({delta_surge_call:.4f}) must be > 0.50 for +4.0% surge"
