"""Phase 6 Unit Test: Full 14-Stage Pipeline Integration Verification."""
import pytest

from option_program.market_data.market_data_adapter import RealMarketDataAdapter
from option_program.runtime.program_runtime import OptionProgramRuntime
from option_program.broker.broker_interface import BrokerFactory, BrokerMode, PaperBrokerAdapter
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime

def test_phase6_full_pipeline_multi_tick_integration():
    """Runs a 100-tick full pipeline integration through all 14 stages."""
    adapter = RealMarketDataAdapter()
    assert adapter.connect() is True

    vssf = VirtualSecuritiesFirmRuntime(initial_capital=50_000_000.0)
    paper_broker = BrokerFactory.create_broker(mode=BrokerMode.PAPER, vssf_runtime=vssf)
    assert isinstance(paper_broker, PaperBrokerAdapter)

    runtime = OptionProgramRuntime()

    orders_count = 0
    ticks_processed = 0

    for i in range(1, 101):
        price = 350.0 + ((i % 10) - 5) * 0.1
        pkt = {
            "seq_id": i,
            "timestamp": f"09:00:{i:02d}.000",
            "timestamp_ns": i * 1000000,
            "underlying_price": round(price, 2),
            "strike_price": 350.0,
            "option_type": "CALL",
            "bid_price": round(price - 0.05, 2),
            "ask_price": round(price + 0.05, 2),
            "last_price": round(price, 2),
            "volume": 100
        }
        tick = adapter.parse_packet(pkt)
        assert tick is not None
        ticks_processed += 1

        vssf.process_market_data(tick)
        commands = runtime.process_tick(tick)
        for cmd in commands:
            orders_count += 1
            paper_broker.send_order(cmd)

    assert ticks_processed == 100
    assert vssf.account.balance > 0
    summary = paper_broker.get_account_summary()
    assert summary.total_balance > 0
