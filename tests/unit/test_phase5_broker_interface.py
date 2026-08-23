"""Phase 5 Unit Test: Dual Broker Interface & Paper Trading Execution Verification."""
import pytest

from shared.contracts.canonical import (
    CanonicalMarketTick,
    CanonicalOrderCommand,
    CanonicalOrderSide,
    CanonicalAssetType,
    CanonicalOptionType
)
from option_program.broker.broker_interface import (
    BrokerMode,
    BrokerFactory,
    PaperBrokerAdapter,
    RealBrokerAdapterStub
)
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime

def test_phase5_broker_interface_and_factory_invariants():
    """Validates PaperBrokerAdapter, RealBrokerAdapterStub, BrokerFactory and VSSF execution."""
    vssf = VirtualSecuritiesFirmRuntime(initial_capital=20_000_000.0)
    tick = CanonicalMarketTick(
        seq_id=1, timestamp="09:00:00.000",
        underlying_price=350.0, last_price=350.0, bid_price=349.95, ask_price=350.05,
        volume=1000, strike_price=350.0
    )
    vssf.process_market_data(tick)

    # 1. Factory Creation (PAPER)
    paper = BrokerFactory.create_broker(mode=BrokerMode.PAPER, vssf_runtime=vssf)
    assert isinstance(paper, PaperBrokerAdapter)
    assert paper.is_connected() is True

    # 2. Normal Order Execution
    cmd = CanonicalOrderCommand(
        client_order_id="TEST-001", track_id="Track1", asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY, qty=1, price=2.50, option_type=CanonicalOptionType.CALL,
        strike=350.0, tag_id="test"
    )
    rep = paper.send_order(cmd)
    assert rep is not None
    assert rep.exec_id.startswith("EXEC-")
    assert rep.executed_price >= 2.50
    assert rep.fee > 0

    # 3. Snapshot and Positions
    summary = paper.get_account_summary()
    assert summary.account_id == "ACC-VSSF-001"
    assert len(paper.get_positions()) > 0

    # 4. Factory Creation (REAL Stub)
    real = BrokerFactory.create_broker(mode=BrokerMode.REAL)
    assert isinstance(real, RealBrokerAdapterStub)
    assert real.is_connected() is False
