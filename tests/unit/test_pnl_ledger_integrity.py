from decimal import Decimal
from core.contracts import verify_account_integrity, OrderPurpose

def test_pnl_account_accounting_equation():
    """Cash Balance = Initial + Realized PnL - Fee - Slippage 회계 등식 검증"""
    initial_cap = Decimal("25000000.00")
    realized_pnl = Decimal("1500000.00")
    total_fee = Decimal("4500.00")
    total_slip = Decimal("12500.00")
    
    # 올바른 Cash Balance 계산
    cash_bal = initial_cap + realized_pnl - total_fee - total_slip
    
    # verify_account_integrity 검증 유틸 호출
    is_valid, msg = verify_account_integrity(
        cash_balance=cash_bal,
        initial_capital=initial_cap,
        realized_pnl=realized_pnl,
        total_fees=total_fee,
        total_slippage=total_slip
    )
    
    assert is_valid is True, f"회계 정합성이 일치해야 합니다: {msg}"

def test_order_purpose_hedge_attribution():
    """OrderPurpose.RISK_HEDGE를 활용한 Strategy PnL vs Hedge PnL 구분 검증"""
    records = [
        {"order_purpose": OrderPurpose.STRATEGY_ENTRY.value, "pnl": 50000.0},
        {"order_purpose": OrderPurpose.STRATEGY_EXIT.value, "pnl": 120000.0},
        {"order_purpose": OrderPurpose.RISK_HEDGE.value, "pnl": -30000.0},
    ]
    
    strategy_pnl = sum(r["pnl"] for r in records if r["order_purpose"] != OrderPurpose.RISK_HEDGE.value)
    hedge_pnl = sum(r["pnl"] for r in records if r["order_purpose"] == OrderPurpose.RISK_HEDGE.value)
    
    assert strategy_pnl == 170000.0
    assert hedge_pnl == -30000.0
    assert (strategy_pnl + hedge_pnl) == 140000.0
