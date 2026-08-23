"""Phase 7 Unit Test: Telemetry & UI Real-time Synchronization Verification."""
import orjson as json
import pytest

from shared.contracts.canonical import (
    CanonicalMarketTick,
    CanonicalOrderCommand,
    CanonicalOrderSide,
    CanonicalAssetType,
    CanonicalOptionType
)
from option_program.broker.broker_interface import BrokerFactory, BrokerMode
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime

def test_phase7_telemetry_packet_and_ui_sync():
    """Validates telemetry packet schema, positions, balance and serialization."""
    vssf = VirtualSecuritiesFirmRuntime(initial_capital=25_000_000.0)
    paper_broker = BrokerFactory.create_broker(mode=BrokerMode.PAPER, vssf_runtime=vssf)

    tick = CanonicalMarketTick(
        seq_id=1, timestamp="09:00:00.000",
        underlying_price=350.0, last_price=350.0, bid_price=349.95, ask_price=350.05,
        volume=1000, strike_price=350.0
    )
    vssf.process_market_data(tick)

    cmd = CanonicalOrderCommand(
        client_order_id="UI-002", track_id="Track1", asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY, qty=1, price=2.50, option_type=CanonicalOptionType.CALL,
        strike=350.0, tag_id="ui_unit_test"
    )
    paper_broker.send_order(cmd)

    summary = paper_broker.get_account_summary()
    assert summary.account_id == "ACC-VSSF-001"
    assert summary.total_balance > 0

    packet = {
        "event_type": "UI_STATE_SNAPSHOT",
        "account": {
            "account_id": summary.account_id,
            "total_balance": summary.total_balance,
            "used_margin": summary.used_margin,
            "free_margin": summary.free_margin
        },
        "positions": summary.positions
    }

    serialized = json.dumps(packet)
    deserialized = json.loads(serialized)
    assert deserialized["account"]["account_id"] == "ACC-VSSF-001"
    assert len(deserialized["positions"]) > 0
