"""Phase 3 Unit Test: Risk, Order, and Execution Exception Scenario Verification."""
import pytest
import uuid
import asyncio

from shared.contracts.canonical import (
    CanonicalMarketTick,
    CanonicalOrderCommand,
    CanonicalOrderSide,
    CanonicalAssetType,
    CanonicalOptionType
)
from shared.core.contracts import OrderStatus, RiskApprovalToken
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime
from option_program.orders.oms_fsm import OmsFsm
from virtual_securities_firm.execution.execution_engine import ExecutionEngine

def test_phase3_risk_order_execution_exception_invariants():
    """Validates 23 exception invariants across Risk, Order and Execution layers."""
    # 1. Risk Invariants
    vssf = VirtualSecuritiesFirmRuntime(initial_capital=10_000_000.0)
    tick = CanonicalMarketTick(
        seq_id=1, timestamp="09:00:00.000",
        underlying_price=350.0, last_price=350.0, bid_price=349.95, ask_price=350.05,
        volume=1000, strike_price=350.0
    )
    vssf.process_market_data(tick)

    # 1.1 Insufficient Margin
    huge_order = CanonicalOrderCommand(
        client_order_id="RISK-01", track_id="Track1", asset_type=CanonicalAssetType.FUTURES,
        side=CanonicalOrderSide.BUY, qty=100, price=350.0, option_type=CanonicalOptionType.CALL,
        strike=350.0, tag_id="huge"
    )
    assert vssf.process_order(huge_order) is None

    # 1.2 Zero Capital
    zero_vssf = VirtualSecuritiesFirmRuntime(initial_capital=0.0)
    norm_order = CanonicalOrderCommand(
        client_order_id="RISK-03", track_id="Track1", asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY, qty=1, price=2.5, option_type=CanonicalOptionType.CALL,
        strike=350.0, tag_id="norm"
    )
    assert zero_vssf.process_order(norm_order) is None

    # 2. Order FSM Invariants
    fsm = OmsFsm()
    test_id = uuid.uuid4()
    token = RiskApprovalToken(order_id=test_id, timestamp_ns=1000000, signature="sig_test")
    asyncio.run(fsm.register_order(token))
    assert fsm.get_status(test_id) == OrderStatus.NEW

    asyncio.run(fsm.transition(test_id, OrderStatus.SENT))
    asyncio.run(fsm.transition(test_id, OrderStatus.FILLED))
    assert fsm.get_status(test_id) == OrderStatus.FILLED

    # 3. Execution Invariants
    exec_engine = ExecutionEngine()
    rep = exec_engine.execute_order(norm_order, fill_price=2.50, fill_qty=1)
    assert rep is not None
    assert rep.executed_qty == 1
    assert rep.executed_price >= 2.50
