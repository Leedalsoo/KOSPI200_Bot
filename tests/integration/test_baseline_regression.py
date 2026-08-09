import os
import sys
import pytest
import orjson
import mock_ws_server as ws

def test_baseline_snapshot_regression():
    """리팩토링 전/후 비교용 Baseline Snapshot 회귀 테스트"""
    snapshot_path = os.path.join("tests", "baseline", "baseline_snapshot_v1.json")
    assert os.path.exists(snapshot_path), "Baseline snapshot file does not exist!"
    
    with open(snapshot_path, "rb") as f:
        baseline = orjson.loads(f.read())
        
    ws._reset_session_state(preserve_capital=False)
    
    # 1. Account Integrity
    assert abs(ws.current_capital - baseline["account"]["current_capital"]) < 1e-5
    assert abs(ws.total_equity - baseline["account"]["total_equity"]) < 1e-5
    
    # 2. PnL Accounting
    realized_pnl = sum(ws.strategy_realized_pnl.values())
    unrealized_pnl = ws.total_equity - ws.current_capital
    net_pnl = ws.total_equity - 25000000.0
    
    assert abs(realized_pnl - baseline["pnl"]["realized_pnl"]) < 1e-5
    assert abs(unrealized_pnl - baseline["pnl"]["unrealized_pnl"]) < 1e-5
    assert abs(net_pnl - baseline["pnl"]["net_pnl"]) < 1e-5
    
    # 3. Guards State
    assert ws.is_market_opened_today == baseline["guards"]["is_market_opened_today"]
    assert ws.already_rolled_this_month == baseline["guards"]["already_rolled_this_month"]
    assert len(ws.portfolio_options) == baseline["positions_count"]
