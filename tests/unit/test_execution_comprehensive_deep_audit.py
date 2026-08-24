"""Unit Test: Execution Engine & Slippage Model Deep Audit Comprehensive Verification."""
import pytest
from virtual_securities_firm.execution.execution_engine import ExecutionEngine, SlippageEngine
from virtual_securities_firm.execution.execution_ui import ExecutionUI
from virtual_market_simulator.market.synthetic_market_generator import VirtualBrokerControlInterface
from shared.contracts.canonical import CanonicalOrderCommand, CanonicalAssetType, CanonicalOrderSide

def test_slippage_model_spread_vol_qty_impact():
    """Validates 3-factor slippage model (Spread, Volatility, Quantity Impact)."""
    control = VirtualBrokerControlInterface()
    control.update_config({"slippage_multiplier": 1.0, "base_spread": 0.05})
    slippage_eng = SlippageEngine(control_interface=control)

    # 1. Base spread impact only (vol=1.0, qty=1)
    # base = 0.05 * 0.3 * 1.0 = 0.015
    # qty_impact = 1 * 0.01 * 1.0 = 0.01
    # total = 0.025
    res1 = slippage_eng.calculate_execution("LIMIT", "BUY", requested_price=2.50, qty=1, current_volatility=1.0, current_spread=0.05)
    assert res1["slippage"] == 0.025
    assert res1["executed_price"] == 2.52 or res1["executed_price"] == 2.53  # rounded to 2.53

    # 2. High Volatility impact (vol=2.0 -> vol_impact = (2.0-1.0)*0.08 = 0.08)
    # total = 0.015 + 0.08 + 0.01 = 0.105
    res2 = slippage_eng.calculate_execution("LIMIT", "BUY", requested_price=2.50, qty=1, current_volatility=2.0, current_spread=0.05)
    assert res2["slippage"] == 0.105

    # 3. High Quantity impact (qty=10 -> qty_impact = 0.10)
    # total = 0.015 + 0.0 + 0.10 = 0.115
    res3 = slippage_eng.calculate_execution("LIMIT", "BUY", requested_price=2.50, qty=10, current_volatility=1.0, current_spread=0.05)
    assert res3["slippage"] == 0.115

def test_krx_commission_1_5bps_precision():
    """Validates KRX standard 1.5bps commission calculation."""
    engine = ExecutionEngine()
    cmd = CanonicalOrderCommand(
        client_order_id="ORD_COMM_1",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=2,
        price=2.0
    )
    report = engine.execute_order(cmd, fill_price=2.0, fill_qty=2)
    # Nominal = 2.0 (or with slippage) * 2 * 250,000 * 0.000015 = 15.0 KRW
    assert report.fee > 0.0
    assert abs(report.fee - (report.executed_price * 2 * 250000 * 0.000015)) < 0.05

def test_buy_vs_sell_slippage_direction():
    """Validates BUY causes upward slippage and SELL causes downward slippage."""
    control = VirtualBrokerControlInterface()
    control.update_config({"slippage_multiplier": 1.0})
    engine = ExecutionEngine(control_interface=control)

    cmd_buy = CanonicalOrderCommand(
        client_order_id="ORD_BUY_1",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=2,
        price=3.00
    )
    rep_buy = engine.execute_order(cmd_buy, fill_price=3.00, fill_qty=2)
    assert rep_buy.executed_price >= 3.00

    cmd_sell = CanonicalOrderCommand(
        client_order_id="ORD_SELL_1",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.SELL,
        qty=2,
        price=3.00
    )
    rep_sell = engine.execute_order(cmd_sell, fill_price=3.00, fill_qty=2)
    assert rep_sell.executed_price <= 3.00

def test_partial_fill_multi_tranche_execution():
    """Validates multi-tranche partial fill reporting."""
    engine = ExecutionEngine()
    cmd = CanonicalOrderCommand(
        client_order_id="ORD_MULTI_1",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=10,
        price=2.50
    )

    r1 = engine.execute_order(cmd, fill_price=2.50, fill_qty=3)
    r2 = engine.execute_order(cmd, fill_price=2.50, fill_qty=4)
    r3 = engine.execute_order(cmd, fill_price=2.50, fill_qty=3)

    assert len(engine.reports) == 3
    assert sum(r.executed_qty for r in engine.reports) == 10
    assert all(r.client_order_id == "ORD_MULTI_1" for r in engine.reports)

def test_execution_ui_dashboard_rendering():
    """Validates ExecutionUI real-time dashboard packet."""
    ui = ExecutionUI()
    engine = ExecutionEngine()
    cmd = CanonicalOrderCommand(
        client_order_id="ORD_UI_1",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=2,
        price=2.50
    )
    rep = engine.execute_order(cmd, fill_price=2.50, fill_qty=2)

    ui.log_execution(rep)
    packet = ui.render_execution_summary()
    assert packet["total_executions"] == 1
    assert len(packet["latest_executions"]) == 1
