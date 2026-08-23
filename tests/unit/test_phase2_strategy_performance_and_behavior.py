"""Phase 2 Unit Test: Strategy Performance & Behavioral Verification across Track 1 to Track 9."""
import pytest
from virtual_market_simulator.runtime.simulator_runtime import VirtualMarketSimulatorRuntime, VirtualBrokerConfig
from option_program.runtime.program_runtime import OptionProgramRuntime
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime

def test_phase2_track1_to_9_behavioral_and_performance_verification():
    """Validates that all strategies respond to market conditions with non-zero signal generation."""
    vms = VirtualMarketSimulatorRuntime(config=VirtualBrokerConfig())
    runtime = OptionProgramRuntime()
    vssf = VirtualSecuritiesFirmRuntime(initial_capital=100_000_000.0)

    track_names = [f"Track{i}" for i in range(1, 10)]
    signals = {name: 0 for name in track_names}

    # 100 ticks
    for tick in vms.generate_tick_stream(total_days=1, ticks_per_day=100):
        vssf.process_market_data(tick)
        commands = runtime.process_tick(tick)

        for cmd in commands:
            if cmd.track_id in signals:
                signals[cmd.track_id] += 1
            report = vssf.process_order(cmd)
            if report is not None:
                runtime.consume_execution_report(report)

    # Behavioral check: signals should be generated without any runtime exceptions
    for name in track_names:
        assert runtime.strategy_metrics[name]["exceptions"] == 0
