"""Phase 4 & Step 2-2: Market Data Anomaly Guard & Invariant Verification Unit Tests.

Verifies the 4 core anomaly handling rules in RealMarketDataAdapter:
1. Stale Tick: Ticks with older timestamps are dropped.
2. Duplicate Tick: Ticks with repeated sequence IDs are dropped.
3. Sequence Gap: Missing sequence intervals are detected and logged while processing continues.
4. Out-of-order Tick: Delayed or reordered sequence/time arrivals are prevented from corrupting runtime state.
"""
import pytest
from datetime import datetime

from option_program.market_data.market_data_adapter import RealMarketDataAdapter
from shared.contracts.canonical import CanonicalMarketTick


def test_stale_tick_is_dropped_and_increments_metric():
    """A. Stale Tick: Verifies that ticks with older timestamps than the latest processed are dropped."""
    adapter = RealMarketDataAdapter()
    adapter.connect()

    # 1. First valid tick at t=2,000,000,000 ns
    pkt1 = {
        "seq_id": 1,
        "timestamp_ns": 2000000000,
        "underlying_price": 350.0,
        "strike_price": 350.0,
        "option_type": "CALL",
        "bid_price": 3.50,
        "ask_price": 3.60,
        "last_price": 3.55,
        "volume": 100
    }
    tick1 = adapter.parse_packet(pkt1)
    assert tick1 is not None
    assert tick1.seq_id == 1
    assert adapter.metrics["parsed_ticks"] == 1
    assert adapter.metrics["stale_ticks_dropped"] == 0

    # 2. Stale tick at t=1,000,000,000 ns with higher seq_id
    pkt_stale = {
        "seq_id": 2,
        "timestamp_ns": 1000000000,  # Older than pkt1
        "underlying_price": 351.0,
        "strike_price": 350.0,
        "option_type": "CALL",
        "bid_price": 3.60,
        "ask_price": 3.70,
        "last_price": 3.65,
        "volume": 50
    }
    tick_stale = adapter.parse_packet(pkt_stale)
    assert tick_stale is None, "Stale tick must be dropped by RealMarketDataAdapter."
    assert adapter.metrics["stale_ticks_dropped"] == 1
    assert adapter.metrics["parsed_ticks"] == 1


def test_duplicate_tick_is_dropped_and_increments_metric():
    """B. Duplicate Tick: Verifies that ticks with duplicate or non-incrementing seq_id are dropped."""
    adapter = RealMarketDataAdapter()
    adapter.connect()

    pkt1 = {
        "seq_id": 10,
        "timestamp_ns": 1000000,
        "underlying_price": 350.0,
        "strike_price": 350.0,
        "option_type": "CALL"
    }
    tick1 = adapter.parse_packet(pkt1)
    assert tick1 is not None
    assert adapter.metrics["duplicate_ticks_dropped"] == 0

    # Duplicate injection with identical seq_id
    tick_dup = adapter.parse_packet(pkt1)
    assert tick_dup is None, "Duplicate seq_id must be dropped."
    assert adapter.metrics["duplicate_ticks_dropped"] == 1

    # Duplicate injection with lower seq_id
    pkt_lower = {
        "seq_id": 9,
        "timestamp_ns": 1000001,
        "underlying_price": 350.0
    }
    tick_lower = adapter.parse_packet(pkt_lower)
    assert tick_lower is None
    assert adapter.metrics["duplicate_ticks_dropped"] == 2


def test_gap_tick_is_detected_and_processing_continues():
    """C. Gap Tick: Verifies that missing sequence gaps are accurately counted and processing continues."""
    adapter = RealMarketDataAdapter()
    adapter.connect()

    # Base tick seq_id = 5
    pkt1 = {"seq_id": 5, "timestamp_ns": 500, "underlying_price": 350.0}
    t1 = adapter.parse_packet(pkt1)
    assert t1 is not None
    assert adapter.metrics["sequence_gaps_detected"] == 0

    # Next tick jumps to seq_id = 8 (missed 6 and 7 -> gap of 2)
    pkt_gap = {"seq_id": 8, "timestamp_ns": 800, "underlying_price": 350.5}
    t_gap = adapter.parse_packet(pkt_gap)
    assert t_gap is not None, "Gap tick should be accepted while registering sequence gap metric."
    assert t_gap.seq_id == 8
    assert adapter.metrics["sequence_gaps_detected"] == 2
    assert adapter.metrics["parsed_ticks"] == 2


def test_out_of_order_tick_sequence_and_time_reversal_guarded():
    """D. Out-of-Order Tick: Verifies sequence and timestamp inversions are safely filtered."""
    adapter = RealMarketDataAdapter()
    adapter.connect()

    # Step 1: seq=1, time=100
    t1 = adapter.parse_packet({"seq_id": 1, "timestamp_ns": 100, "underlying_price": 350.0})
    assert t1 is not None

    # Step 2: seq=3, time=300 arrives first (gap=1 detected)
    t3 = adapter.parse_packet({"seq_id": 3, "timestamp_ns": 300, "underlying_price": 352.0})
    assert t3 is not None
    assert adapter.metrics["sequence_gaps_detected"] == 1

    # Step 3: Delayed seq=2 arrives late (seq 2 <= 3 -> duplicate/reversal drop)
    t2_delayed = adapter.parse_packet({"seq_id": 2, "timestamp_ns": 200, "underlying_price": 351.0})
    assert t2_delayed is None, "Delayed out-of-order seq_id <= last_seq_id must be dropped."
    assert adapter.metrics["duplicate_ticks_dropped"] == 1

    # Step 4: seq=4 arrives with inverted timestamp (time=250 < 300 -> stale drop)
    t4_inverted_time = adapter.parse_packet({"seq_id": 4, "timestamp_ns": 250, "underlying_price": 353.0})
    assert t4_inverted_time is None, "Timestamp inversion must be dropped as stale."
    assert adapter.metrics["stale_ticks_dropped"] == 1
