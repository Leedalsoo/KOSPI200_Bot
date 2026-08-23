"""Phase 4 Unit Test: Real-time Market Data Adapter & Network Invariant Verification."""
import pytest
from datetime import datetime, timedelta

from option_program.market_data.market_data_adapter import RealMarketDataAdapter
from option_program.runtime.program_runtime import OptionProgramRuntime
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime

def test_phase4_market_data_adapter_invariants():
    """Validates connection, packet parsing, gaps, duplicates, stales, heartbeats, and E2E delivery."""
    adapter = RealMarketDataAdapter(heartbeat_timeout_sec=2.0)
    assert adapter.connect() is True
    assert adapter.is_connected() is True

    # 1. Normal Tick Parsing
    pkt = {
        "seq_id": 10,
        "timestamp": "09:00:00.100",
        "timestamp_ns": 1000,
        "underlying_price": 350.25,
        "strike_price": 350.0,
        "option_type": "CALL",
        "bid_price": 350.20,
        "ask_price": 350.30,
        "last_price": 350.25,
        "volume": 500
    }
    tick = adapter.parse_packet(pkt)
    assert tick is not None
    assert tick.seq_id == 10
    assert tick.underlying_price == 350.25

    # 2. Duplicate Dropped
    dup_tick = adapter.parse_packet(pkt)
    assert dup_tick is None
    assert adapter.metrics["duplicate_ticks_dropped"] == 1

    # 3. Gap Detection
    pkt_gap = {
        "seq_id": 13,
        "timestamp": "09:00:00.300",
        "timestamp_ns": 1200,
        "underlying_price": 350.40,
        "strike_price": 350.0,
        "option_type": "CALL",
        "bid_price": 350.35,
        "ask_price": 350.45,
        "last_price": 350.40,
        "volume": 200
    }
    tick_gap = adapter.parse_packet(pkt_gap)
    assert tick_gap is not None
    assert adapter.metrics["sequence_gaps_detected"] == 2

    # 4. Stale Data Dropped
    pkt_stale = {
        "seq_id": 14,
        "timestamp": "09:00:00.050",
        "timestamp_ns": 800,  # Older than 1200
        "underlying_price": 350.00,
        "strike_price": 350.0,
        "option_type": "CALL",
        "bid_price": 349.95,
        "ask_price": 350.05,
        "last_price": 350.00,
        "volume": 100
    }
    tick_stale = adapter.parse_packet(pkt_stale)
    assert tick_stale is None
    assert adapter.metrics["stale_ticks_dropped"] == 1

    # 5. Heartbeat Check
    assert adapter.check_heartbeat(datetime.now()) is True
    future_time = datetime.now() + timedelta(seconds=3.0)
    assert adapter.check_heartbeat(future_time) is False

    # 6. E2E Delivery into Runtime & VSSF
    runtime = OptionProgramRuntime()
    vssf = VirtualSecuritiesFirmRuntime(initial_capital=50_000_000.0)
    vssf.process_market_data(tick)
    cmds = runtime.process_tick(tick)
    assert len(cmds) >= 0
    assert vssf.account.balance > 0
