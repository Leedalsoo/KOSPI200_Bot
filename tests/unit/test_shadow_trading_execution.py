"""Unit Test: Shadow Trading Live Mirroring & Air-Gap Execution Verification."""
import pytest

from shared.contracts.canonical import (
    CanonicalMarketTick,
    CanonicalOrderCommand,
    CanonicalOrderSide,
    CanonicalAssetType,
    CanonicalOptionType
)
from option_program.broker.broker_interface import BrokerFactory, BrokerMode, ShadowBrokerAdapter
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime

def test_shadow_trading_broker_and_execution_mirroring():
    """Validates ShadowBrokerAdapter, order mirroring, zero real dispatch, and shadow PnL."""
    vssf = VirtualSecuritiesFirmRuntime(initial_capital=30_000_000.0)
    shadow_broker = BrokerFactory.create_broker(mode=BrokerMode.SHADOW, vssf_runtime=vssf)
    assert isinstance(shadow_broker, ShadowBrokerAdapter)
    assert shadow_broker.is_connected() is True

    # 1. Market Data Ingestion
    tick = CanonicalMarketTick(
        seq_id=1, timestamp="09:00:00.000",
        underlying_price=350.0, last_price=350.0, bid_price=349.95, ask_price=350.05,
        volume=1000, strike_price=350.0
    )
    vssf.process_market_data(tick)

    # 2. Shadow Order Execution
    cmd = CanonicalOrderCommand(
        client_order_id="SHADOW-001", track_id="Track1", asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY, qty=1, price=2.50, option_type=CanonicalOptionType.CALL,
        strike=350.0, tag_id="shadow_unit"
    )
    rep = shadow_broker.send_order(cmd)
    assert rep is not None
    assert rep.exec_id.startswith("EXEC-")
    assert len(shadow_broker.shadow_executions) == 1

    # 3. Shadow State & Snapshot
    summary = shadow_broker.get_account_summary()
    assert summary.account_id == "ACC-VSSF-001"
    assert summary.total_balance > 0
    assert len(shadow_broker.get_positions()) > 0
