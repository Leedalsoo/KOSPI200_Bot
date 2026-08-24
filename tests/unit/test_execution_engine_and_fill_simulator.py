"""Unit Test: Authoritative Execution Engine & Slippage Fill Simulator."""
import pytest
from decimal import Decimal

from shared.contracts.canonical import (
    CanonicalOrderCommand,
    CanonicalExecutionReport,
    CanonicalAssetType,
    CanonicalOrderSide,
    CanonicalOptionType
)
from virtual_securities_firm.execution.execution_engine import ExecutionEngine, SlippageEngine
from virtual_market_simulator.market.synthetic_market_generator import VirtualBrokerControlInterface

def test_full_fill_execution():
    """Validates full fill order execution and execution report issuance."""
    engine = ExecutionEngine()
    cmd = CanonicalOrderCommand(
        client_order_id="ORD-FILL-001",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=5,
        price=2.50,
        option_type=CanonicalOptionType.CALL,
        strike=350.0,
        tag_id="T1"
    )

    report = engine.execute_order(cmd, fill_price=2.50, fill_qty=5)
    assert isinstance(report, CanonicalExecutionReport)
    assert report.client_order_id == "ORD-FILL-001"
    assert report.executed_qty == 5
    assert report.executed_price >= 2.50  # BUY slippage adds to price
    assert report.fee > 0.0

def test_partial_fill_execution():
    """Validates partial fill order execution and proportional fee calculation."""
    engine = ExecutionEngine()
    cmd = CanonicalOrderCommand(
        client_order_id="ORD-PARTIAL-001",
        track_id="Track2",
        asset_type=CanonicalAssetType.FUTURES,
        side=CanonicalOrderSide.BUY,
        qty=10,
        price=350.0,
        tag_id="T2"
    )

    # Partial fill of 4 contracts out of 10
    report = engine.execute_order(cmd, fill_price=350.0, fill_qty=4)
    assert report.executed_qty == 4
    # Expected fee for 4 contracts: 350.0 * 4 * 250,000 * 0.000015 = 5250 KRW
    assert report.fee >= 5250.0

def test_slippage_calculation_buy_sell():
    """Validates that BUY slippage increases price and SELL slippage decreases price."""
    slip_engine = SlippageEngine()

    # BUY -> executed_price >= requested_price
    buy_res = slip_engine.calculate_execution(
        order_type="LIMIT",
        side="BUY",
        requested_price=2.50,
        qty=2,
        current_spread=0.05
    )
    assert buy_res["executed_price"] >= 2.50

    # SELL -> executed_price <= requested_price
    sell_res = slip_engine.calculate_execution(
        order_type="LIMIT",
        side="SELL",
        requested_price=2.50,
        qty=2,
        current_spread=0.05
    )
    assert sell_res["executed_price"] <= 2.50

def test_volatility_and_quantity_slippage_impact():
    """Validates that higher volatility scale and higher quantity result in greater slippage."""
    slip_engine = SlippageEngine()

    # Low vol (1.0) & low qty (1)
    base_res = slip_engine.calculate_execution(
        order_type="LIMIT",
        side="BUY",
        requested_price=350.0,
        qty=1,
        current_volatility=1.0
    )

    # High vol (2.0) & high qty (50)
    high_impact_res = slip_engine.calculate_execution(
        order_type="LIMIT",
        side="BUY",
        requested_price=350.0,
        qty=50,
        current_volatility=2.0
    )

    assert high_impact_res["slippage"] > base_res["slippage"]
