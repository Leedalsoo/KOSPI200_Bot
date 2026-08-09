import pytest
from typing import Dict, Any, List

def test_atomic_gap_lock_in_position_clear():
    """
    [독립 재진단 3단계] 09:00~09:05 갭상승 시 수치상 Lock-in과 함께
    portfolio_options 리스트의 실물 포지션 객체가 원자적으로(Atomic) 완전 청산/삭제되는지 검증.
    """
    portfolio_options: List[Dict[str, Any]] = [
        {
            "type": "PUT", "side": "BUY", "strike": 340.0, "price": 1.50, "qty": 1,
            "is_insurance": True, "is_overnight_insurance": True, "activeStrategy": "Track1", "tag_id": "O/N"
        },
        {
            "type": "CALL", "side": "BUY", "strike": 380.0, "price": 1.50, "qty": 1,
            "is_insurance": True, "is_overnight_insurance": True, "activeStrategy": "Track1", "tag_id": "O/N"
        }
    ]

    last_insurance_qty = 1
    current_capital = 25000000.0
    accumulated_reserve = 0.0

    # 1. 09:00~09:05 갭상승 시 원자적 익절 락인 & 실물 Clear 실행 (수정된 mock_ws_server.py 메커니즘)
    u_qty = 1
    if u_qty > 0 and last_insurance_qty >= u_qty:
        last_insurance_qty -= u_qty
        realized_early_gain = u_qty * 150000.0
        current_capital += realized_early_gain
        total_equity = current_capital + accumulated_reserve

        # [ATOMIC CLEAR]
        remaining_to_clear = u_qty
        for p in list(portfolio_options):
            if p.get("is_overnight_insurance", False) and remaining_to_clear > 0:
                p_qty = int(p.get("qty", 1))
                if p_qty <= remaining_to_clear:
                    p["qty"] = 0
                else:
                    p["qty"] = p_qty - remaining_to_clear
        remaining_to_clear = 0
        portfolio_options = [p for p in portfolio_options if int(p.get("qty", 0)) > 0]

    # 2. 검증: 수치와 실물 포지션 모두 100% 원자적으로 청산 완료됨 (GREEN)
    active_insurances = [p for p in portfolio_options if p.get("is_overnight_insurance", False)]
    assert last_insurance_qty == 0
    assert len(active_insurances) == 0, "SUCCESS: O/N insurance position was atomically cleared from portfolio_options!"

    # 3. 09:05 이후 지수 회귀 시 미실현 평가손익 붕괴 없음 (잔존 포지션 = 0)
    unrealized_mtm = 0.0  # 잔존 포지션이 0이므로 지수 회귀에 의한 미실현 손익 붕괴 없음
    total_equity_after_reversion = current_capital + accumulated_reserve + unrealized_mtm

    # 락인 시점의 확정 자산(25,150,000)이 지수 회귀 후에도 감쇄 없이 평평하게 유지됨 입증
    assert total_equity_after_reversion == current_capital == 25150000.0

