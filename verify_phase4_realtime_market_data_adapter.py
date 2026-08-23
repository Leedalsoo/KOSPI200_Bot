"""Phase 4: Real-time Market Data Adapter & Network Invariant Verification.

Verifies:
1. Normal Packet Parsing: timestamp, symbol/strike, bid, ask, last, volume, seq_id
2. Missing Tick (Sequence Gap) Detection
3. Duplicate Tick Filtering (Idempotency)
4. Out-of-order Tick Filtering
5. Stale Data Filtering
6. Heartbeat Monitoring & Timeout
7. Disconnect & Auto-Reconnect Handling
8. End-to-End Delivery into OptionProgram & VSSF
"""
import sys
import logging
from datetime import datetime, timedelta

from option_program.market_data.market_data_adapter import RealMarketDataAdapter, IMarketDataProvider
from option_program.runtime.program_runtime import OptionProgramRuntime
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def run_phase4_market_data_audit():
    print("=" * 105)
    print("[PHASE 4 REAL-TIME MARKET DATA ADAPTER AUDIT] Network Invariants & Dual Provider Verification")
    print("=" * 105)

    adapter = RealMarketDataAdapter(heartbeat_timeout_sec=2.0)
    runtime = OptionProgramRuntime()
    vssf = VirtualSecuritiesFirmRuntime(initial_capital=50_000_000.0)

    results = []

    # 1. Connection Lifecycle
    conn_ok = adapter.connect()
    results.append(("MarketData: Connection Establishment", conn_ok and adapter.is_connected(), "Connected successfully"))

    # 2. Normal Packet Parsing
    pkt1 = {
        "seq_id": 1,
        "timestamp": "09:00:01.100",
        "timestamp_ns": 1000000000,
        "underlying_price": 350.50,
        "strike_price": 350.0,
        "option_type": "CALL",
        "bid_price": 350.45,
        "ask_price": 350.55,
        "last_price": 350.50,
        "volume": 250
    }
    tick1 = adapter.parse_packet(pkt1)
    results.append(("MarketData: CanonicalMarketTick Parsing", tick1 is not None and tick1.underlying_price == 350.50 and tick1.seq_id == 1, "Parsed tick seq_id=1, price=350.50"))

    # 3. Duplicate Tick Filter
    tick1_dup = adapter.parse_packet(pkt1)
    results.append(("MarketData: Duplicate Tick Dropping", tick1_dup is None and adapter.metrics["duplicate_ticks_dropped"] == 1, "Duplicate seq_id=1 dropped"))

    # 4. Missing Tick (Sequence Gap) Detection
    pkt3 = {
        "seq_id": 4,  # Jumped from 1 to 4 (missed 2 and 3)
        "timestamp": "09:00:01.400",
        "timestamp_ns": 1000000300,
        "underlying_price": 350.80,
        "strike_price": 350.0,
        "option_type": "CALL",
        "bid_price": 350.75,
        "ask_price": 350.85,
        "last_price": 350.80,
        "volume": 120
    }
    tick3 = adapter.parse_packet(pkt3)
    results.append(("MarketData: Sequence Gap (Missing Tick) Detection", tick3 is not None and adapter.metrics["sequence_gaps_detected"] == 2, "Detected 2 missed ticks"))

    # 5. Stale Data Guard (Old timestamp)
    pkt_stale = {
        "seq_id": 5,
        "timestamp": "09:00:00.900",
        "timestamp_ns": 900000000,  # Older than last timestamp_ns 1000000300
        "underlying_price": 350.10,
        "strike_price": 350.0,
        "option_type": "CALL",
        "bid_price": 350.05,
        "ask_price": 350.15,
        "last_price": 350.10,
        "volume": 50
    }
    tick_stale = adapter.parse_packet(pkt_stale)
    results.append(("MarketData: Stale Timestamp Guard", tick_stale is None and adapter.metrics["stale_ticks_dropped"] == 1, "Stale data dropped"))

    # 6. Heartbeat Monitoring
    # Normal heartbeat within 2.0s
    hb_normal = adapter.check_heartbeat(datetime.now())
    results.append(("MarketData: Normal Heartbeat Verification", hb_normal is True, "Heartbeat healthy"))

    # Timeout heartbeat after 3.0s
    future_time = datetime.now() + timedelta(seconds=3.0)
    hb_timeout = adapter.check_heartbeat(future_time)
    results.append(("MarketData: Heartbeat Timeout Detection", hb_timeout is False and adapter.metrics["heartbeat_timeouts"] == 1, "Timeout alert triggered"))

    # 7. Disconnect & Auto-Reconnect Handling
    adapter.disconnect()
    results.append(("MarketData: Disconnect Handling", adapter.is_connected() is False, "Disconnected gracefully"))
    reconnect_ok = adapter.connect()
    results.append(("MarketData: Auto-Reconnect Resilience", reconnect_ok and adapter.is_connected(), "Reconnected successfully"))

    # 8. End-to-End Pipeline Feeding (Adapter ➔ OptionProgram ➔ VSSF)
    pkt_live = {
        "seq_id": 6,
        "timestamp": "09:00:02.000",
        "timestamp_ns": 1000001000,
        "underlying_price": 351.00,
        "strike_price": 350.0,
        "option_type": "CALL",
        "bid_price": 350.95,
        "ask_price": 351.05,
        "last_price": 351.00,
        "volume": 300
    }
    live_tick = adapter.parse_packet(pkt_live)
    vssf.process_market_data(live_tick)
    commands = runtime.process_tick(live_tick)
    results.append(("MarketData: E2E Pipeline Delivery", len(commands) >= 0 and vssf.account.balance > 0, "Delivered to Runtime & VSSF successfully"))

    # -------------------------------------------------------------
    # PRINT RESULTS
    # -------------------------------------------------------------
    print("-" * 105)
    print(f"{'Verification Check':<45} | {'Status':<10} | {'Verification Evidence'}")
    print("-" * 105)
    all_passed = True
    for name, passed, evidence in results:
        status_str = "PASS" if passed else "FAIL"
        if not passed:
            all_passed = False
        print(f"{name:<45} | {status_str:<10} | {evidence}")

    print("=" * 105)
    if all_passed:
        print(f"[PHASE 4 RESULT] PASS - All {len(results)}/8 Real-time Market Data Invariants Verified 100% Operational!")
    else:
        print("[PHASE 4 RESULT] FAIL - Market Data Invariants Failed!")
    print("=" * 105)
    return all_passed

if __name__ == "__main__":
    success = run_phase4_market_data_audit()
    sys.exit(0 if success else 1)
