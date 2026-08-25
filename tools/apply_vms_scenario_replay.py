from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCENARIO_ENGINE = '''"""Scenario-driven market tick parameter source."""
from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


@dataclass(frozen=True)
class ScenarioAdjustment:
    volatility_multiplier: float = 1.0
    drift: float = 0.0
    gap_pct: float = 0.0
    shock_delta: float = 0.0


class ScenarioEngine:
    """Loads market-generation scenarios and produces deterministic adjustments."""

    def __init__(self, config_path: Optional[str] = None, seed: int = 42) -> None:
        self.config_path = Path(config_path or "config/market_scenarios.yaml")
        self.seed = seed
        self._rng = random.Random(seed)
        self._scenarios: Dict[str, Dict[str, Any]] = {}
        self._active_name = ""
        self._load()

    def _load(self) -> None:
        with self.config_path.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
        scenarios = payload.get("scenarios") or {}
        if not isinstance(scenarios, dict) or not scenarios:
            raise ValueError("market_scenarios.yaml must define scenarios")
        self._scenarios = {str(name): dict(value or {}) for name, value in scenarios.items()}
        active = str(payload.get("active_scenario") or next(iter(self._scenarios)))
        self.set_scenario(active)

    @property
    def active_scenario(self) -> str:
        return self._active_name

    @property
    def available_scenarios(self) -> tuple[str, ...]:
        return tuple(self._scenarios)

    def set_scenario(self, name: str) -> None:
        if name not in self._scenarios:
            raise ValueError(f"unsupported scenario: {name}")
        self._active_name = name
        self._rng = random.Random(self.seed)

    def next_adjustment(self, tick_index: int, ticks_per_day: int) -> ScenarioAdjustment:
        cfg = self._scenarios[self._active_name]
        base_volatility = float(cfg.get("base_volatility", 1.0))
        drift_range = cfg.get("trend_drift_range", [-0.03, 0.03])
        gap_range = cfg.get("gap_magnitude_percent", [0.0, 0.0])
        shock_range = cfg.get("biweekly_shock_range", [0.0, 0.0])
        interval_days = max(1, int(cfg.get("shock_interval_days", 999999)))
        drift = self._rng.uniform(float(drift_range[0]), float(drift_range[1]))
        gap_pct = 0.0
        shock_delta = 0.0
        interval_ticks = max(1, interval_days * max(1, ticks_per_day))
        if tick_index > 0 and tick_index % interval_ticks == 0:
            magnitude = self._rng.uniform(float(shock_range[0]), float(shock_range[1]))
            direction = -1.0 if self._rng.random() < 0.5 else 1.0
            shock_delta = magnitude * direction
            gap = self._rng.uniform(float(gap_range[0]), float(gap_range[1])) / 100.0
            gap_pct = gap * direction
        return ScenarioAdjustment(max(0.01, base_volatility), drift, gap_pct, shock_delta)

    def state(self) -> Dict[str, Any]:
        return {"active_scenario": self._active_name, "available_scenarios": list(self.available_scenarios)}
'''

REPLAY_ENGINE = '''"""Canonical tick replay source."""
from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import List, Optional

from shared.contracts.canonical import CanonicalMarketTick


class HistoricalReplayEngine:
    """Deterministic in-memory replay source for canonical market ticks."""

    def __init__(self, ticks: Optional[Iterable[CanonicalMarketTick]] = None) -> None:
        self._ticks: List[CanonicalMarketTick] = list(ticks or [])
        self._cursor = 0

    @property
    def active(self) -> bool:
        return bool(self._ticks)

    @property
    def exhausted(self) -> bool:
        return self._cursor >= len(self._ticks)

    @property
    def cursor(self) -> int:
        return self._cursor

    def load(self, ticks: Iterable[CanonicalMarketTick]) -> None:
        self._ticks = list(ticks)
        self._cursor = 0

    def clear(self) -> None:
        self._ticks = []
        self._cursor = 0

    def reset(self) -> None:
        self._cursor = 0

    def next_tick(self) -> Optional[CanonicalMarketTick]:
        if self.exhausted:
            return None
        tick = self._ticks[self._cursor]
        self._cursor += 1
        return tick

    def __iter__(self) -> Iterator[CanonicalMarketTick]:
        while True:
            tick = self.next_tick()
            if tick is None:
                return
            yield tick
'''

RUNTIME = '''"""Virtual Market Simulator Runtime with scenario/replay tick supply."""
from __future__ import annotations

import logging
import random
from typing import Any, Dict, Generator, Iterable, Optional

from shared.contracts.canonical import CanonicalMarketTick
from virtual_market_simulator.market.synthetic_market_generator import VirtualBrokerConfig, VirtualBrokerControlInterface
from virtual_market_simulator.engine.clock_controller import VMSClockController
from virtual_market_simulator.engine.vms_state_manager import VMSStateManager
from virtual_market_simulator.scenario.replay_engine import HistoricalReplayEngine
from virtual_market_simulator.scenario.scenario_engine import ScenarioEngine

logger = logging.getLogger(__name__)


class VirtualMarketSimulatorRuntime:
    """Production VMS: market generation, scenario source and replay source."""

    _SPEED_TO_REPLAY = {"SLOW": 1, "NORMAL": 300, "FAST": 1000}

    def __init__(self, config: Optional[VirtualBrokerConfig] = None) -> None:
        self.config = config or VirtualBrokerConfig()
        self.control = VirtualBrokerControlInterface(config=self.config)
        self.clock = VMSClockController()
        self.state_mgr = VMSStateManager()
        self.scenario = ScenarioEngine()
        self.replay = HistoricalReplayEngine()
        self._price = 350.0
        self._initial_price = 350.0
        self._volume = 10
        self._volatility_ratio = 1.0
        self._market_regime = "NORMAL"
        self._running = True
        self._tick_speed = "NORMAL"
        self._stress_type: Optional[str] = None
        self._pending_gap_pct = 0.0
        self._pending_shock_delta = 0.0
        self._rng = random.Random(42)

    def set_generator_config(self, base_price: float, volatility_ratio: float, spread: float, volume: float) -> Dict[str, Any]:
        if base_price <= 0: raise ValueError("base_price must be greater than 0")
        if volatility_ratio <= 0: raise ValueError("volatility_ratio must be greater than 0")
        if spread < 0: raise ValueError("spread must not be negative")
        if volume < 0: raise ValueError("volume must not be negative")
        self._price = float(base_price)
        self._initial_price = float(base_price)
        self._volatility_ratio = float(volatility_ratio)
        self.config.volatility_scale = float(volatility_ratio)
        self.config.base_spread = float(spread)
        self._volume = int(volume)
        return self.get_control_state()

    def set_market_regime(self, regime: str) -> Dict[str, Any]:
        allowed = {"NORMAL", "BULL", "BEAR", "SIDEWAYS", "VOLATILE", "CRISIS"}
        if regime not in allowed: raise ValueError(f"unsupported market regime: {regime}")
        self._market_regime = regime
        return self.get_control_state()

    def set_running(self, running: bool) -> Dict[str, Any]:
        self._running = bool(running)
        return self.get_control_state()

    def set_scenario(self, scenario: str) -> Dict[str, Any]:
        self.scenario.set_scenario(scenario)
        return self.get_control_state()

    def load_replay(self, ticks: Iterable[CanonicalMarketTick]) -> Dict[str, Any]:
        self.replay.load(ticks)
        return self.get_control_state()

    def clear_replay(self) -> Dict[str, Any]:
        self.replay.clear()
        return self.get_control_state()

    def reset_simulation(self) -> Dict[str, Any]:
        self.config = VirtualBrokerConfig()
        self.control = VirtualBrokerControlInterface(config=self.config)
        self.clock = VMSClockController()
        self.state_mgr = VMSStateManager()
        self.scenario = ScenarioEngine()
        self.replay.clear()
        self._price = 350.0
        self._initial_price = 350.0
        self._volume = 10
        self._volatility_ratio = 1.0
        self._market_regime = "NORMAL"
        self._running = False
        self._tick_speed = "NORMAL"
        self._stress_type = None
        self._pending_gap_pct = 0.0
        self._pending_shock_delta = 0.0
        self._rng = random.Random(42)
        return self.get_control_state()

    def inject_market_stress(self, type: str) -> Dict[str, Any]:
        allowed = {"VOL_SPIKE", "LIQUIDITY_DROP", "GAP", "CRASH", "FLASH_MOVE"}
        if type not in allowed: raise ValueError(f"unsupported market stress: {type}")
        self._stress_type = type
        if type == "GAP": self._pending_gap_pct = 0.02
        elif type == "CRASH": self._pending_gap_pct = -0.05
        elif type == "FLASH_MOVE": self._pending_gap_pct = self._rng.choice((-0.03, 0.03))
        return self.get_control_state()

    def clear_market_stress(self) -> Dict[str, Any]:
        self._stress_type = None
        self._pending_gap_pct = 0.0
        self._pending_shock_delta = 0.0
        return self.get_control_state()

    def set_tick_speed(self, speed: str) -> Dict[str, Any]:
        if speed not in self._SPEED_TO_REPLAY: raise ValueError(f"unsupported tick speed: {speed}")
        self._tick_speed = speed
        self.config.replay_speed = self._SPEED_TO_REPLAY[speed]
        return self.get_control_state()

    def get_control_state(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "source": "REPLAY" if self.replay.active else "SCENARIO",
            "scenario": self.scenario.state(),
            "replay": {"active": self.replay.active, "cursor": self.replay.cursor, "exhausted": self.replay.exhausted},
            "generator": {"base_price": self._initial_price, "volatility_ratio": self._volatility_ratio, "spread": self.config.base_spread, "volume": self._volume},
            "market_regime": self._market_regime,
            "stress": self._stress_type,
            "tick_speed": self._tick_speed,
            "config": self.control.get_config(),
        }

    def _price_delta(self, scenario_drift: float = 0.0, scenario_volatility: float = 1.0) -> float:
        scale = self._volatility_ratio * scenario_volatility
        if self._market_regime == "BULL": delta = self._rng.uniform(0.10, 0.60) * scale
        elif self._market_regime == "BEAR": delta = self._rng.uniform(-0.60, -0.10) * scale
        elif self._market_regime == "SIDEWAYS": delta = self._rng.uniform(-0.25, 0.25) * scale
        elif self._market_regime == "VOLATILE": delta = self._rng.uniform(-0.90, 0.90) * scale
        elif self._market_regime == "CRISIS": delta = self._rng.uniform(-1.20, 0.30) * scale
        else: delta = self._rng.uniform(-0.35, 0.35) * scale
        return delta + scenario_drift

    def _next_market_tick(self, tick_index: int = 0, ticks_per_day: int = 500) -> CanonicalMarketTick:
        adjustment = self.scenario.next_adjustment(tick_index, ticks_per_day)
        gap_pct = self._pending_gap_pct or adjustment.gap_pct
        if gap_pct:
            self._price = max(100.0, round(self._price * (1.0 + gap_pct), 2))
            self._pending_gap_pct = 0.0
        delta = self._price_delta(adjustment.drift, adjustment.volatility_multiplier) + adjustment.shock_delta
        if self._stress_type == "VOL_SPIKE": delta *= 3.0
        elif self._stress_type == "FLASH_MOVE": delta *= 2.5
        self._price = max(100.0, round(self._price + delta, 2))
        spread = max(0.05, min(1.0, float(self.config.base_spread)))
        if self._stress_type == "LIQUIDITY_DROP": spread = min(1.0, spread * 3.0)
        bid = round(self._price - spread / 2.0, 2)
        ask = round(self._price + spread / 2.0, 2)
        volume = max(1, int(self._volume * 0.25)) if self._stress_type == "LIQUIDITY_DROP" else self._volume
        seq = self.state_mgr.next_sequence()
        timestamp = self.clock.get_time_str()
        self.clock.advance_tick(500)
        return CanonicalMarketTick(timestamp=timestamp, underlying_price=self._price, strike_price=round(self._price / 2.5) * 2.5, option_type="CALL", bid_price=bid, ask_price=ask, last_price=self._price, volume=volume, seq_id=seq)

    def step(self) -> Dict[str, Any]:
        tick = self.replay.next_tick() if self.replay.active else self._next_market_tick(0, 500)
        if tick is None: raise StopIteration("replay exhausted")
        return {"timestamp": tick.timestamp, "price": tick.underlying_price, "bid": tick.bid_price, "ask": tick.ask_price, "volume": tick.volume, "seq_id": tick.seq_id}

    def generate_tick_stream(self, total_days: int = 1250, ticks_per_day: int = 500) -> Generator[CanonicalMarketTick, None, None]:
        for tick_index in range(total_days * ticks_per_day):
            if not self._running: return
            if self.replay.active:
                tick = self.replay.next_tick()
                if tick is None: return
                yield tick
            else:
                yield self._next_market_tick(tick_index, ticks_per_day)
'''

TESTS = '''from datetime import datetime
from shared.contracts.canonical import CanonicalMarketTick
from virtual_market_simulator.runtime.simulator_runtime import VirtualMarketSimulatorRuntime


def _tick(seq: int, price: float) -> CanonicalMarketTick:
    return CanonicalMarketTick(timestamp=datetime(2026, 8, 23, 9, 0, seq), underlying_price=price, strike_price=350.0, option_type="CALL", bid_price=price - 0.1, ask_price=price + 0.1, last_price=price, volume=10, seq_id=seq)


def test_scenario_source_is_default_and_produces_ticks():
    runtime = VirtualMarketSimulatorRuntime()
    runtime.set_scenario("CALM")
    runtime.set_running(True)
    ticks = list(runtime.generate_tick_stream(total_days=1, ticks_per_day=5))
    assert len(ticks) == 5
    assert runtime.get_control_state()["source"] == "SCENARIO"


def test_scenario_selection_is_deterministic():
    a = VirtualMarketSimulatorRuntime(); b = VirtualMarketSimulatorRuntime()
    a.set_scenario("HIGH_VOLATILITY"); b.set_scenario("HIGH_VOLATILITY")
    ta = list(a.generate_tick_stream(total_days=1, ticks_per_day=10))
    tb = list(b.generate_tick_stream(total_days=1, ticks_per_day=10))
    assert [x.underlying_price for x in ta] == [x.underlying_price for x in tb]


def test_replay_source_overrides_scenario_generation():
    runtime = VirtualMarketSimulatorRuntime()
    runtime.load_replay([_tick(101, 401.0), _tick(102, 402.0), _tick(103, 403.0)])
    runtime.set_running(True)
    ticks = list(runtime.generate_tick_stream(total_days=1, ticks_per_day=10))
    assert [t.seq_id for t in ticks] == [101, 102, 103]
    assert [t.underlying_price for t in ticks] == [401.0, 402.0, 403.0]


def test_replay_reset_restarts_from_first_tick():
    runtime = VirtualMarketSimulatorRuntime()
    runtime.load_replay([_tick(1, 401.0), _tick(2, 402.0)])
    runtime.set_running(True)
    first = list(runtime.generate_tick_stream(total_days=1, ticks_per_day=2))
    runtime.replay.reset()
    second = list(runtime.generate_tick_stream(total_days=1, ticks_per_day=2))
    assert [t.seq_id for t in first] == [1, 2]
    assert [t.seq_id for t in second] == [1, 2]


def test_reset_clears_replay_and_stops_runtime():
    runtime = VirtualMarketSimulatorRuntime()
    runtime.load_replay([_tick(1, 401.0)])
    runtime.reset_simulation()
    state = runtime.get_control_state()
    assert state["source"] == "SCENARIO"
    assert state["replay"]["active"] is False
    assert state["running"] is False
'''

FILES = {
    "virtual_market_simulator/scenario/scenario_engine.py": SCENARIO_ENGINE,
    "virtual_market_simulator/scenario/replay_engine.py": REPLAY_ENGINE,
    "virtual_market_simulator/runtime/simulator_runtime.py": RUNTIME,
    "tests/unit/test_vms_scenario_replay.py": TESTS,
}


def main() -> None:
    for relative_path, content in FILES.items():
        path = ROOT / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        backup = path.with_name(path.name + ".bak_stage4")
        if path.exists():
            backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        path.write_text(content, encoding="utf-8")
        print(f"Applied: {relative_path}")
        if backup.exists(): print(f"Backup : {backup.relative_to(ROOT)}")


if __name__ == "__main__":
    main()