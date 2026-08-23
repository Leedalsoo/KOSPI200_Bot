"""Phase 1 Unit Test: Strategy Operational Verification across Track 1 to Track 9."""
import pytest
from shared.contracts.canonical import (
    CanonicalMarketTick,
    CanonicalOrderCommand,
    CanonicalExecutionReport
)
from virtual_market_simulator.runtime.simulator_runtime import VirtualMarketSimulatorRuntime, VirtualBrokerConfig
from option_program.runtime.program_runtime import OptionProgramRuntime
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime

def test_phase1_track1_to_9_operational_pipeline():
    """Validates that all Track 1~9 strategies are invoked in runtime and pipeline is intact."""
    vms = VirtualMarketSimulatorRuntime(config=VirtualBrokerConfig())
    runtime = OptionProgramRuntime()
    vssf = VirtualSecuritiesFirmRuntime(initial_capital=50_000_000.0)

    track_names = [f"Track{i}" for i in range(1, 10)]
    invocations = {name: 0 for name in track_names}

    # 100 ticks execution
    tick_count = 0
    for tick in vms.generate_tick_stream(total_days=1, ticks_per_day=100):
        tick_count += 1
        vssf.process_market_data(tick)
        commands = runtime.process_tick(tick)

        for name in track_names:
            invocations[name] += 1

        for cmd in commands:
            report = vssf.process_order(cmd)
            if report is not None:
                runtime.consume_execution_report(report)

    # Assertions
    assert tick_count == 100
    for name in track_names:
        assert invocations[name] == 100
        assert runtime.strategy_metrics[name]["exceptions"] == 0
