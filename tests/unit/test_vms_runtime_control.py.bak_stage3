from virtual_market_simulator.runtime.simulator_runtime import VirtualMarketSimulatorRuntime


def test_generator_control_changes_runtime_tick():
    runtime = VirtualMarketSimulatorRuntime()
    runtime.set_generator_config(500.0, 1.0, 0.20, 25)
    tick = next(runtime.generate_tick_stream(total_days=1, ticks_per_day=1))
    assert tick.underlying_price >= 100.0
    assert tick.volume == 25
    assert round(tick.ask_price - tick.bid_price, 2) == 0.20


def test_market_regime_is_used_by_runtime():
    runtime = VirtualMarketSimulatorRuntime()
    runtime.set_generator_config(350.0, 1.0, 0.05, 10)
    runtime.set_market_regime("BULL")
    first = next(runtime.generate_tick_stream(total_days=1, ticks_per_day=1))
    second = next(runtime.generate_tick_stream(total_days=1, ticks_per_day=1))
    assert second.underlying_price > first.underlying_price


def test_market_stress_changes_generated_tick():
    runtime = VirtualMarketSimulatorRuntime()
    runtime.set_generator_config(350.0, 1.0, 0.05, 100)
    runtime.inject_market_stress("LIQUIDITY_DROP")
    tick = next(runtime.generate_tick_stream(total_days=1, ticks_per_day=1))
    assert tick.volume == 25
    assert round(tick.ask_price - tick.bid_price, 2) == 0.15


def test_tick_speed_updates_runtime_control_state():
    runtime = VirtualMarketSimulatorRuntime()
    runtime.set_tick_speed("FAST")
    state = runtime.get_control_state()
    assert state["tick_speed"] == "FAST"
    assert state["config"]["replay_speed"] == 1000


def test_reset_restores_vms_defaults():
    runtime = VirtualMarketSimulatorRuntime()
    runtime.set_generator_config(500.0, 2.0, 0.2, 50)
    runtime.set_market_regime("BEAR")
    runtime.inject_market_stress("CRASH")
    state = runtime.reset_simulation()
    assert state["generator"]["base_price"] == 350.0
    assert state["generator"]["volatility_ratio"] == 1.0
    assert state["generator"]["spread"] == 0.05
    assert state["generator"]["volume"] == 10
    assert state["market_regime"] == "NORMAL"
    assert state["stress"] is None
    assert state["tick_speed"] == "NORMAL"
