"""Unit Test: Portfolio & Position Management Comprehensive Verification."""
import pytest
from virtual_securities_firm.position.position_manager import PositionManager

def test_position_initial_open():
    """Validates initial position opening and state."""
    pm = PositionManager()
    pnl = pm.update_position("OPT_CALL_350", "BUY", qty=2, price=2.50)
    assert pnl == 0.0
    assert "OPT_CALL_350" in pm.positions
    pos = pm.positions["OPT_CALL_350"]
    assert pos["qty"] == 2
    assert pos["avg_price"] == 2.50
    assert pos["side"] == "BUY"

def test_position_scale_in_weighted_avg_price():
    """Validates weighted average price calculation on scale-in."""
    pm = PositionManager()
    # 1. First Buy: 2 contracts @ 2.0
    pm.update_position("OPT_CALL_350", "BUY", qty=2, price=2.0)
    # 2. Second Buy: 3 contracts @ 3.0
    # Expected avg_price: (2*2.0 + 3*3.0) / 5 = (4.0 + 9.0) / 5 = 2.60
    pm.update_position("OPT_CALL_350", "BUY", qty=3, price=3.0)

    pos = pm.positions["OPT_CALL_350"]
    assert pos["qty"] == 5
    assert pos["avg_price"] == 2.60

def test_position_partial_unwind_pnl():
    """Validates partial unwind retains avg_price and generates correct realized PnL."""
    pm = PositionManager()
    # Open 5 contracts @ 2.0
    pm.update_position("OPT_PUT_340", "BUY", qty=5, price=2.0)

    # Sell 2 contracts @ 3.0 (Profit = (3.0 - 2.0) * 2 * 250,000 = 500,000 KRW)
    pnl = pm.update_position("OPT_PUT_340", "SELL", qty=2, price=3.0)
    assert pnl == 500_000.0

    pos = pm.positions["OPT_PUT_340"]
    assert pos["qty"] == 3
    assert pos["avg_price"] == 2.0  # Avg price remains unchanged on partial exit

def test_position_full_flatten_removal():
    """Validates full flatten removes the position key from state."""
    pm = PositionManager()
    pm.update_position("OPT_CALL_355", "BUY", qty=4, price=1.50)
    pnl = pm.update_position("OPT_CALL_355", "SELL", qty=4, price=2.0)
    assert pnl == 500_000.0
    assert "OPT_CALL_355" not in pm.positions

def test_mixed_futures_and_options_portfolio():
    """Validates concurrent tracking of mixed futures and options multi-leg portfolio."""
    pm = PositionManager()

    # Futures Long
    pm.update_position("FUTURES_101V", "BUY", qty=2, price=350.0)
    # Option Call Long
    pm.update_position("OPT_CALL_350", "BUY", qty=5, price=2.50)
    # Option Put Long
    pm.update_position("OPT_PUT_345", "BUY", qty=5, price=1.80)

    assert len(pm.positions) == 3
    assert pm.positions["FUTURES_101V"]["qty"] == 2
    assert pm.positions["OPT_CALL_350"]["qty"] == 5
    assert pm.positions["OPT_PUT_345"]["qty"] == 5

def test_position_flip():
    """Validates position flip from Net Long to Net Short."""
    pm = PositionManager()
    # Long 2 contracts @ 2.0
    pm.update_position("OPT_CALL_350", "BUY", qty=2, price=2.0)

    # Sell 5 contracts @ 3.0 -> Closes 2 Longs (+500,000 KRW) and opens 3 Shorts @ 3.0
    pnl = pm.update_position("OPT_CALL_350", "SELL", qty=5, price=3.0)
    assert pnl == 500_000.0

    pos = pm.positions["OPT_CALL_350"]
    assert pos["qty"] == 3
    assert pos["avg_price"] == 3.0
    assert pos["side"] == "SELL"
