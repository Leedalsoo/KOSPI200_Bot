"""Unit Test: Market Data Adapter Resilience, Sequence Invariants & Failure Recovery."""
import pytest
from datetime import datetime, timedelta

from option_program.market_data.market_data_adapter import RealMarketDataAdapter
from shared.contracts.canonical import CanonicalMarketTick

def test_connection_lifecycle_and_auto_reconnect():
    """Validates connect, disconnect, and automatic reconnect on packet arrival."""
    adapter = RealMarketDataAdapter(auto_reconnect=True)
    assert adapter.is_connected() is False

    # 1. Connect
    assert adapter.connect() is True
    assert adapter.is_connected() is True

    # 2. Disconnect
    adapter.disconnect()
    assert adapter.is_connected() is False

    # 3. Auto-reconnect on packet
    pkt = {"seq_id": 1, "timestamp_ns": 1000, "underlying_price": 350.0}
    tick = adapter.parse_packet(pkt)
    assert tick is not None
    assert adapter.is_connected() is True
    assert adapter.get_metrics()["parsed_ticks"] == 1
    assert adapter.get_metrics()["reconnect_events"] >= 2

def test_duplicate_and_sequence_gap_handling():
    """Validates that duplicate ticks are dropped and sequence gaps are strictly tracked."""
    adapter = RealMarketDataAdapter()
    adapter.connect()

    # Tick 1
    t1 = adapter.parse_packet({"seq_id": 10, "timestamp_ns": 1000, "underlying_price": 350.0})
    assert t1 is not None

    # Duplicate Tick (seq_id 10 <= 10)
    t1_dup = adapter.parse_packet({"seq_id": 10, "timestamp_ns": 1001, "underlying_price": 350.0})
    assert t1_dup is None
    assert adapter.get_metrics()["duplicate_ticks_dropped"] == 1

    # Older Duplicate Tick (seq_id 8 <= 10)
    t_old = adapter.parse_packet({"seq_id": 8, "timestamp_ns": 1002, "underlying_price": 350.0})
    assert t_old is None
    assert adapter.get_metrics()["duplicate_ticks_dropped"] == 2

    # Sequence Gap (seq_id 15: missed 11, 12, 13, 14 = 4 ticks)
    t_gap = adapter.parse_packet({"seq_id": 15, "timestamp_ns": 1003, "underlying_price": 350.5})
    assert t_gap is not None
    assert adapter.get_metrics()["sequence_gaps_detected"] == 4

def test_stale_and_out_of_order_timestamps():
    """Validates that stale ticks with timestamp regression are dropped."""
    adapter = RealMarketDataAdapter()
    adapter.connect()

    # Normal Tick
    t1 = adapter.parse_packet({"seq_id": 1, "timestamp_ns": 5000, "underlying_price": 350.0})
    assert t1 is not None

    # Stale Tick (timestamp_ns 4000 < 5000)
    t_stale = adapter.parse_packet({"seq_id": 2, "timestamp_ns": 4000, "underlying_price": 350.0})
    assert t_stale is None
    assert adapter.get_metrics()["stale_ticks_dropped"] == 1

def test_malformed_and_negative_price_guard():
    """Validates that negative prices or corrupted payloads are rejected safely without raising unhandled exceptions."""
    adapter = RealMarketDataAdapter()
    adapter.connect()

    # Negative price
    t_neg = adapter.parse_packet({"seq_id": 1, "underlying_price": -350.0})
    assert t_neg is None

    # Malformed non-numeric
    t_bad = adapter.parse_packet({"seq_id": 2, "underlying_price": "NOT_A_PRICE"})
    assert t_bad is None

def test_heartbeat_timeout_and_auto_recovery():
    """Validates heartbeat monitor timeout detection and auto-recovery triggering."""
    adapter = RealMarketDataAdapter(heartbeat_timeout_sec=2.0, auto_reconnect=True)
    adapter.connect()

    # Recent tick -> Heartbeat OK
    now = datetime.now()
    adapter.parse_packet({"seq_id": 1, "underlying_price": 350.0})
    assert adapter.check_heartbeat(current_time=now) is True

    # 3 seconds later -> Heartbeat Timeout -> Reconnects
    future_time = now + timedelta(seconds=3.0)
    assert adapter.check_heartbeat(current_time=future_time) is False
    assert adapter.get_metrics()["heartbeat_timeouts"] == 1
    assert adapter.is_connected() is True  # Auto-reconnected

def test_high_throughput_long_run_stream():
    """Validates high-throughput stream processing without data corruption or memory degradation."""
    adapter = RealMarketDataAdapter()
    adapter.connect()

    for i in range(1, 10001):
        pkt = {
            "seq_id": i,
            "timestamp_ns": i * 1000,
            "underlying_price": 350.0 + (i % 10) * 0.05,
            "strike_price": 350.0,
            "option_type": "CALL",
            "volume": 100
        }
        tick = adapter.parse_packet(pkt)
        assert tick is not None

    metrics = adapter.get_metrics()
    assert metrics["parsed_ticks"] == 10000
    assert metrics["duplicate_ticks_dropped"] == 0
    assert metrics["sequence_gaps_detected"] == 0
    assert metrics["stale_ticks_dropped"] == 0
