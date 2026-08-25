from virtual_market_simulator.runtime.simulator_runtime import VirtualMarketSimulatorRuntime


def test_step_scenario_tick_index_progresses(monkeypatch) -> None:
    runtime = VirtualMarketSimulatorRuntime()
    runtime.set_scenario("CALM")
    runtime.set_running(True)

    indices = []
    original = runtime.scenario.next_adjustment

    def capture_index(tick_index: int, ticks_per_day: int):
        indices.append(tick_index)
        return original(tick_index, ticks_per_day)

    monkeypatch.setattr(runtime.scenario, "next_adjustment", capture_index)

    runtime.step()
    runtime.step()
    runtime.step()

    assert indices == [0, 1, 2]