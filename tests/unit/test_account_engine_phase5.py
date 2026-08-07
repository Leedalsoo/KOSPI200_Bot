# -*- coding: utf-8 -*-
from decimal import Decimal
from account.account_engine import AccountEngine

def test_account_engine_integrity() -> None:
    account = AccountEngine(initial_capital=Decimal("25000000.00"))
    
    # 1. 거래 실현 (PnL +1,000,000, Fee 1,500, Slippage 500)
    account.apply_realized_trade(pnl=Decimal("1000000.00"), fee=Decimal("1500.00"), slippage=Decimal("500.00"))
    
    # Cash = 25,000,000 + 1,000,000 - 1,500 - 500 = 25,998,000.00
    assert account.cash == Decimal("25998000.00")
    
    # 무결성 검증 PASS 확인
    is_valid, msg = account.verify_integrity()
    assert is_valid is True
    assert msg == "OK"

    # 2. 증거금 2,000,000원 설정 후 가용 자금 / Equity 계산 검증
    account.update_margin_and_unrealized(used_margin=Decimal("2000000.00"), unrealized_pnl=Decimal("500000.00"))
    snap = account.get_snapshot()
    
    assert snap.total_equity == Decimal("26498000.00")  # 25,998,000 + 500,000
    assert snap.available_funds == Decimal("23998000.00")  # 25,998,000 - 2,000,000
    assert snap.available_margin == Decimal("23998000.00")
