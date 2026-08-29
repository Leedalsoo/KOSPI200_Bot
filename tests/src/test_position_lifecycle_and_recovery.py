import pytest
from virtual_securities_firm.position.position_manager import PositionManager

MULTIPLIER = 250000.0

def approx(a, b, tol=1e-5):
    return abs(a - b) < tol

def test_position_lifecycle_and_recovery():
    pm = PositionManager()
    symbol = "TEST"
    # 1. create BUY 1 @100
    pnl1 = pm.update_position(symbol=symbol, side="BUY", qty=1, price=100.0)
    assert pnl1 == 0.0
    pos = pm.positions.get(symbol)
    assert pos["qty"] == 1
    assert approx(pos["avg_price"], 100.0)
    assert pos["side"] == "BUY"

    # 2. increase BUY 2 @120
    pnl2 = pm.update_position(symbol=symbol, side="BUY", qty=2, price=120.0)
    assert pnl2 == 0.0
    pos = pm.positions.get(symbol)
    assert pos["qty"] == 3
    # weighted average price = (1*100 + 2*120)/3 = 113.333333...
    assert approx(pos["avg_price"], (1*100 + 2*120)/3)
    assert pos["side"] == "BUY"

    # 3. reduce SELL 1 @130 (partial close)
    pnl3 = pm.update_position(symbol=symbol, side="SELL", qty=1, price=130.0)
    # realized pnl = (130 - avg_price) * close_qty * multiplier
    expected_pnl3 = (130.0 - pos["avg_price"]) * 1 * MULTIPLIER
    assert approx(pnl3, expected_pnl3)
    pos = pm.positions.get(symbol)
    assert pos["qty"] == 2
    assert pos["side"] == "BUY"
    # avg_price remains unchanged for remaining qty
    assert approx(pos["avg_price"], (1*100 + 2*120)/3)

    # 4. close SELL 2 @110 (should close remaining 2 and remove position)
    pnl4 = pm.update_position(symbol=symbol, side="SELL", qty=2, price=110.0)
    # close_qty = min(existing_qty=2, qty=2) =2, realized pnl = (price - avg_price?) Since side BUY, realized = (price - avg_price)*close_qty*multiplier
    expected_pnl4 = (110.0 - pos["avg_price"]) * 2 * MULTIPLIER
    assert approx(pnl4, expected_pnl4)
    # position should be removed
    assert symbol not in pm.positions

    # 5. recovery test: create a new position, snapshot, modify, restore
    pm.update_position(symbol=symbol, side="BUY", qty=2, price=100.0)
    import copy
    snapshot = copy.deepcopy(pm.positions)
    # modify position: change qty via sell
    pm.update_position(symbol=symbol, side="SELL", qty=1, price=120.0)
    # ensure changed
    assert pm.positions[symbol]["qty"] == 1
    # restore snapshot
    pm.positions = snapshot
    restored = pm.positions.get(symbol)
    assert restored["qty"] == 2
    assert approx(restored["avg_price"], 100.0)
    assert restored["side"] == "BUY"
