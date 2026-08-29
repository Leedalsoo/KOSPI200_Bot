import pytest
from virtual_securities_firm.account.paper_account import PaperTradingAccount


def test_strategy_attribution_same_symbol_position_and_margin():
    account = PaperTradingAccount()
    symbol = "TEST"

    account.apply_execution(
        "Track1", side="BUY", qty=1, price=100.0, fee=0.0,
        symbol=symbol, client_order_id="ORD-A"
    )
    account.apply_execution(
        "Track2", side="BUY", qty=1, price=120.0, fee=0.0,
        symbol=symbol, client_order_id="ORD-B"
    )

    assert account.positions[symbol]["qty"] == 2
    assert account.get_order_position("ORD-A")["qty"] == 1
    assert account.get_order_position("ORD-B")["qty"] == 1
    assert account.get_order_position("ORD-A")["avg_price"] == pytest.approx(100.0)
    assert account.get_order_position("ORD-B")["avg_price"] == pytest.approx(120.0)
    assert account.get_order_margin("ORD-A") == pytest.approx(25_000_000.0)
    assert account.get_order_margin("ORD-B") == pytest.approx(30_000_000.0)
