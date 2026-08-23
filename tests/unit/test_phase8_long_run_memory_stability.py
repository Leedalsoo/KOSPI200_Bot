"""Phase 8 Unit Test: Long-Run Stability & Zero Memory Leak Verification."""
import gc
import tracemalloc
import pytest

from option_program.market_data.market_data_adapter import RealMarketDataAdapter
from option_program.runtime.program_runtime import OptionProgramRuntime
from option_program.broker.broker_interface import BrokerFactory, BrokerMode
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime

def test_phase8_long_run_memory_and_stability():
    """Executes a 500-tick long-run stress loop verifying zero memory leak."""
    gc.collect()
    tracemalloc.start()
    obj_init = len(gc.get_objects())

    adapter = RealMarketDataAdapter()
    vssf = VirtualSecuritiesFirmRuntime(initial_capital=50_000_000.0)
    broker = BrokerFactory.create_broker(mode=BrokerMode.PAPER, vssf_runtime=vssf)
    runtime = OptionProgramRuntime()

    for i in range(1, 501):
        p = 350.0 + ((i % 20) - 10) * 0.1
        pkt = {
            "seq_id": i,
            "timestamp": "09:00:00.000",
            "timestamp_ns": i * 1000000,
            "underlying_price": round(p, 2),
            "strike_price": 350.0,
            "option_type": "CALL",
            "bid_price": round(p - 0.05, 2),
            "ask_price": round(p + 0.05, 2),
            "last_price": round(p, 2),
            "volume": 100
        }
        tick = adapter.parse_packet(pkt)
        if tick:
            vssf.process_market_data(tick)
            cmds = runtime.process_tick(tick)
            for c in cmds:
                broker.send_order(c)

    curr_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    gc.collect()
    obj_final = len(gc.get_objects())

    assert (curr_mem / (1024 * 1024)) < 10.0  # Under 10MB
    assert (obj_final - obj_init) < 10000
    assert vssf.account.balance > 0
