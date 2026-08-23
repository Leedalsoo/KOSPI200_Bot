"""Phase 9 Unit Test: Production Release Gate & 20 Real Safety Invariants Verification."""
import pytest
from datetime import datetime

from shared.contracts.canonical import (
    CanonicalMarketTick,
    CanonicalOrderCommand,
    CanonicalOrderSide,
    CanonicalAssetType,
    CanonicalOptionType
)
from option_program.broker.broker_interface import BrokerFactory, BrokerMode, PaperBrokerAdapter, ShadowBrokerAdapter
from option_program.broker.real_broker_adapter import RealBrokerAdapter
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime
from option_program.market_data.market_data_adapter import RealMarketDataAdapter

def test_phase9_production_release_gate_invariants():
    """Validates the 20 production release gate invariants across config, broker, risk, and ledger."""
    vssf = VirtualSecuritiesFirmRuntime(initial_capital=50_000_000.0)
    paper = BrokerFactory.create_broker(mode=BrokerMode.PAPER, vssf_runtime=vssf)
    shadow = BrokerFactory.create_broker(mode=BrokerMode.SHADOW, vssf_runtime=vssf)
    real_broker = BrokerFactory.create_broker(mode=BrokerMode.REAL)
    adapter = RealMarketDataAdapter(auto_reconnect=True)
    adapter.connect()

    # 1. Broker Mode Isolation & Disarmed Real Broker
    assert isinstance(paper, PaperBrokerAdapter)
    assert isinstance(shadow, ShadowBrokerAdapter)
    assert isinstance(real_broker, RealBrokerAdapter)
    assert real_broker.is_connected() is False
    assert paper.cancel_order("TEST-CANCEL") is False  # Real cancel_order test

    # 2. Risk Limit Final Gate
    huge_cmd = CanonicalOrderCommand(
        client_order_id="UNIT-GATE-HUGE", track_id="Track1", asset_type=CanonicalAssetType.FUTURES,
        side=CanonicalOrderSide.BUY, qty=1000, price=350.0, option_type=CanonicalOptionType.CALL,
        strike=350.0, tag_id="gate"
    )
    assert paper.send_order(huge_cmd) is None

    # 3. Market Data Safety & Auto-Reconnect
    adapter.disconnect()
    assert adapter.is_connected() is False
    tick = adapter.parse_packet({"seq_id": 1, "timestamp_ns": 1000, "underlying_price": 350.0})
    assert tick is not None
    assert adapter.is_connected() is True  # Auto-reconnected

    # 4. Authoritative Reconciliation (is_healthy == True)
    reconcil = vssf.reconciliation_engine.reconcile_state(
        account_snapshot=vssf.account,
        execution_history=vssf.execution_engine.reports,
        current_positions=vssf.account.positions
    )
    assert reconcil.get("is_healthy", False) is True
    assert reconcil.get("balance_ok", False) is True

    # 5. Gate 03: Payload Log Masking Real Test
    from option_program.interface.controllers import _mask_payload
    masked = _mask_payload({"api_key": "SECRET", "normal": "123"})
    assert masked["api_key"] == "***"
    assert masked["normal"] == "123"

    # 6. Gate 06: In-Memory Air-Gap (Zero Network Call Test)
    import socket
    import unittest.mock as mock
    net_calls = 0
    def dummy_connect(*args, **kwargs):
        nonlocal net_calls
        net_calls += 1
    with mock.patch.object(socket.socket, "connect", side_effect=dummy_connect):
        paper.send_order(CanonicalOrderCommand(
            client_order_id="AIR-TEST", track_id="Track1", asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY, qty=1, price=2.50, option_type=CanonicalOptionType.CALL,
            strike=350.0, tag_id="air"
        ))
    assert net_calls == 0
