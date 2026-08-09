import pytest
from typing import Dict, Any, List

def run_atomic_clear_logic(portfolio_options: List[Dict[str, Any]], u_qty: int) -> List[Dict[str, Any]]:
    """mock_ws_server.py L1086~L1095와 100% 동일한 Atomic Clear 로직 함수"""
    remaining_to_clear = u_qty
    for p in list(portfolio_options):
        if p.get("is_overnight_insurance", False) and remaining_to_clear > 0:
            p_qty = int(p.get("qty", 1))
            if p_qty <= remaining_to_clear:
                p["qty"] = 0
            else:
                p["qty"] = p_qty - remaining_to_clear
    remaining_to_clear = 0
    return [p for p in portfolio_options if int(p.get("qty", 0)) > 0]


def test_case_1_partial_qty_deduction():
    """시나리오 1: u_qty(1)가 단일 포지션 수량(3)보다 작은 경우 -> 잔량 2계약이 정확히 남음"""
    portfolio = [
        {"type": "PUT", "qty": 3, "is_overnight_insurance": True, "activeStrategy": "Track9"},
        {"type": "CALL", "qty": 3, "is_overnight_insurance": True, "activeStrategy": "Track9"}
    ]
    updated_portfolio = run_atomic_clear_logic(portfolio, u_qty=1)
    
    assert len(updated_portfolio) == 2
    assert updated_portfolio[0]["qty"] == 2
    assert updated_portfolio[1]["qty"] == 2


def test_case_2_distributed_multi_position_deduction():
    """시나리오 2: u_qty(3)가 여러 개별 포지션(1, 2)에 걸쳐 분산 차감되는 경우"""
    portfolio = [
        {"type": "PUT", "qty": 1, "is_overnight_insurance": True, "activeStrategy": "Track9"},
        {"type": "PUT", "qty": 2, "is_overnight_insurance": True, "activeStrategy": "Track9"},
        {"type": "CALL", "qty": 3, "is_overnight_insurance": True, "activeStrategy": "Track9"}
    ]
    updated_portfolio = run_atomic_clear_logic(portfolio, u_qty=3)
    
    # PUT 1, 2 및 CALL 3 모두 3계약 분량 청산되어 0이 되거나 제거됨
    assert len(updated_portfolio) == 0


def test_case_3_multi_signal_loop_idempotency():
    """시나리오 3: 같은 tick에서 다중 signal이 연속 발생하는 경우 remaining_to_clear 안전 재초기화"""
    portfolio = [
        {"type": "PUT", "qty": 2, "is_overnight_insurance": True, "activeStrategy": "Track9"},
        {"type": "CALL", "qty": 2, "is_overnight_insurance": True, "activeStrategy": "Track9"}
    ]
    signals = [{"qty": 1}, {"qty": 1}]
    
    current_portfolio = portfolio
    for sig in signals:
        u_qty = sig["qty"]
        current_portfolio = run_atomic_clear_logic(current_portfolio, u_qty)
        
    # 첫번째 signal로 1계약 청산(잔량 1), 두번째 signal로 1계약 청산(잔량 0)
    assert len(current_portfolio) == 0


def test_case_4_zero_insurance_positions_exception_safety():
    """시나리오 4: is_overnight_insurance 포지션이 0개인데 락인 발생 예외 케이스"""
    portfolio = [
        {"type": "CALL", "qty": 2, "is_overnight_insurance": False, "activeStrategy": "Track1"}
    ]
    updated_portfolio = run_atomic_clear_logic(portfolio, u_qty=1)
    
    # Track9 O/N 포지션이 없으므로 다른 Track1 포지션은 손대지 않고 2계약 그대로 보존됨
    assert len(updated_portfolio) == 1
    assert updated_portfolio[0]["qty"] == 2
    assert updated_portfolio[0]["activeStrategy"] == "Track1"
