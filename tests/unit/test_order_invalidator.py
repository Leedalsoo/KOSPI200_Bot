# -*- coding: utf-8 -*-
import pytest
from risk.order_invalidator import OrderInvalidationEngine, InvalidationReason

def test_c_level_risk_priority_override():
    engine = OrderInvalidationEngine(max_margin_ratio=90.0, max_daily_drawdown_pct=15.0)
    
    order = {"entry_price": 350.0}
    account_state = {"margin_ratio": 95.0, "daily_loss_pct": 5.0, "risk_engine_locked": False}
    market_state = {"current_price": 350.0, "circuit_breaker": False}
    position_state = {"parent_active": True}
    
    res = engine.evaluate_invalidation(order, account_state, market_state, position_state)
    assert res["should_cancel"] is True
    assert "C (RISK_LIMIT)" in res["priority_level"]
    assert res["action"] == "CANCEL_ALL_BROADCAST"

def test_d_level_dynamic_atr_precondition():
    engine = OrderInvalidationEngine()
    
    order = {"entry_price": 350.0}
    account_state = {"margin_ratio": 50.0, "daily_loss_pct": 0.0}
    market_state = {"current_price": 355.0, "daily_atr": 1.5} # stop_pts = max(1.5, 1.8) = 1.8. 2x = 3.6pt. diff = 5.0pt
    position_state = {"parent_active": True}
    
    res = engine.evaluate_invalidation(order, account_state, market_state, position_state)
    assert res["should_cancel"] is True
    assert "D (PRECONDITION)" in res["priority_level"]
    assert res["action"] == "CANCEL_AND_REEVALUATE"

def test_a_level_partial_fill_recalculation():
    engine = OrderInvalidationEngine()
    
    order = {"entry_price": 350.0, "partial_fill_qty": 6, "total_order_qty": 10}
    account_state = {"margin_ratio": 50.0, "daily_loss_pct": 0.0}
    market_state = {"current_price": 350.5, "daily_atr": 1.0}
    position_state = {"parent_active": True}
    
    res = engine.evaluate_invalidation(order, account_state, market_state, position_state)
    assert res["should_cancel"] is False
    assert res["action"] == "RECALCULATE_AND_REISSUE"
    assert res["new_qty"] == 6

def test_all_clear():
    engine = OrderInvalidationEngine()
    
    order = {"entry_price": 350.0, "elapsed_seconds": 100}
    account_state = {"margin_ratio": 40.0, "daily_loss_pct": 0.0}
    market_state = {"current_price": 350.5, "daily_atr": 1.0}
    position_state = {"parent_active": True}
    
    res = engine.evaluate_invalidation(order, account_state, market_state, position_state)
    assert res["should_cancel"] is False
    assert res["action"] == "KEEP_ACTIVE"
