from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOOLS = ROOT / "tools"
TESTS = ROOT / "tests" / "src"
TOOLS.mkdir(parents=True, exist_ok=True)
TESTS.mkdir(parents=True, exist_ok=True)

TEST_CONTENT = """from virtual_market_simulator.runtime.simulator_runtime import VirtualMarketSimulatorRuntime


def test_step_scenario_tick_index_progresses(monkeypatch) -> None:
    runtime = VirtualMarketSimulatorRuntime()
    runtime.set_scenario(\"CALM\")
    runtime.set_running(True)

    indices = []
    original = runtime.scenario.next_adjustment

    def capture_index(tick_index: int, ticks_per_day: int):
        indices.append(tick_index)
        return original(tick_index, ticks_per_day)

    monkeypatch.setattr(runtime.scenario, \"next_adjustment\", capture_index)

    runtime.step()
    runtime.step()
    runtime.step()

    assert indices == [0, 1, 2]
"""

APPLY_CONTENT = """from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / \"virtual_market_simulator\" / \"runtime\" / \"simulator_runtime.py\"
TEST = ROOT / \"tests\" / \"src\" / \"test_vms_scenario_replay_step.py\"

text = RUNTIME.read_text(encoding=\"utf-8\")
backup = RUNTIME.with_suffix(RUNTIME.suffix + \".bak_stage4_step\")
backup.write_text(text, encoding=\"utf-8\")

old = \"self._rng = random.Random(42)\\n\\n    def set_generator_config\"
new = \"self._rng = random.Random(42)\\n        self._scenario_step_index = 0\\n\\n    def set_generator_config\"
if old not in text:
    raise SystemExit(\"init patch target not found\")
text = text.replace(old, new, 1)

old = \"self._rng = random.Random(42)\\n        return self.get_control_state()\\n\\n    def inject_market_stress\"
new = \"self._rng = random.Random(42)\\n        self._scenario_step_index = 0\\n        return self.get_control_state()\\n\\n    def inject_market_stress\"
if old not in text:
    raise SystemExit(\"reset patch target not found\")
text = text.replace(old, new, 1)

old = \"\"\"    def step(self) -> Dict[str, Any]:
        if self.replay.active:
            tick = self.replay.next_tick()
            if tick is None:
                raise StopIteration(\"replay exhausted\")
        else:
            tick = self._next_market_tick(0, 500)
        return {\"\"\"
new = \"\"\"    def step(self) -> Dict[str, Any]:
        if self.replay.active:
            tick = self.replay.next_tick()
            if tick is None:
                raise StopIteration(\"replay exhausted\")
        else:
            tick = self._next_market_tick(self._scenario_step_index, 500)
            self._scenario_step_index += 1
        return {\"\"\"
if old not in text:
    raise SystemExit(\"step patch target not found\")
text = text.replace(old, new, 1)

RUNTIME.write_text(text, encoding=\"utf-8\")
print(f\"Applied: {RUNTIME.relative_to(ROOT)}\")
print(f\"Backup : {backup.relative_to(ROOT)}\")

TEST.write_text(TEST_CONTENT, encoding=\"utf-8\")
print(f\"Applied: {TEST.relative_to(ROOT)}\")
"""

