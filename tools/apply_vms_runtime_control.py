from pathlib import Path

RUNTIME = Path("virtual_market_simulator/runtime/simulator_runtime.py")
TEST = Path("tests/unit/test_vms_runtime_control.py")
RUNTIME_BACKUP = RUNTIME.with_suffix(RUNTIME.suffix + ".bak_stage3")
TEST_BACKUP = TEST.with_suffix(TEST.suffix + ".bak_stage3")

RUNTIME_CONTENT = r'''"""Virtual Market Simulator Runtime - market data generation and UI control."""
import logging
import random
from typing import Any, Dict, Generator, Optional

from shared.contracts.canonical import CanonicalMarketTick
from virtual_market_simulator.market.synthetic_market_generator import (
    VirtualBrokerConfig,
    VirtualBrokerControlInterface,
)
from virtual_market_simulator.engine.clock_controller import VMSClockController
from virtual_market_simulator.engine.vms_state_manager import VMSStateManager

logger = logging.getLogger(__name__)


class VirtualMarketSimulatorRuntime:
    """Production VMS: 시장 데이터 생성과 VMS 제어 상태를 담당한다."""

    _SPEED_TO_REPLAY = {"SLOW": 1, "NORMAL": 300, "FAST": 1000}

    def __init__(self, config: Optional[VirtualBrokerConfig] = None) -> None:
        self.config = config or VirtualBrokerConfig()
        self.control = VirtualBrokerControlInterface(config=self.config)
        self.clock = VMSClockController()
        self.state_mgr = VMSStateManager()
        self._price = 350.0
        self._initial_price = 350.0
        self._volume = 10
        self._volatility_ratio = 1.0
        self._market_regime = "NORMAL"
        self._running = True
        self._tick_speed = "NORMAL"
        self._stress_type: Optional[str] = None
        self._pending_gap_pct = 0.0
        self._rng = random.Random(42)

    def set_generator_config(self, base_price: float, volatility_ratio: float, spread: float, volume: float) -> Dict[str, Any]:
        if base_price <= 0:
            raise ValueError("base_price must be greater than 0")
        if volatility_ratio <= 0:
            raise ValueError("volatility_ratio must be greater than 0")
        if spread < 0:
            raise ValueError("spread must not be negative")
        if volume < 0:
            raise ValueError("volume must not be negative")
        self._price = float(base_price)
        self._initial_price = float(base_price)
        self._volatility_ratio = float(volatility_ratio)
        self.config.volatility_scale = float(volatility_ratio)
        self.config.base_spread = float(spread)
        self._volume = int(volume)
        return self.get_control_state()

    def set_market_regime(self, regime: str) -> Dict[str, Any]:
        allowed = {"NORMAL", "BULL", "BEAR", "SIDEWAYS", "VOLATILE", "CRISIS"}
        if regime not in allowed:
            raise ValueError(f"unsupported market regime: {regime}")
        self._market_regime = regime
        return self.get_control_state()

    def set_running(self, running: bool) -> Dict[str, Any]:
        self._running = bool(running)
        return self.get_control_state()

    def reset_simulation(self) -> Dict[str, Any]:
        self.config = VirtualBrokerConfig()
        self.control = VirtualBrokerControlInterface(config=self.config)
        self.clock = VMSClockController()
        self.state_mgr = VMSStateManager()
        self._price = 350.0
        self._initial_price = 350.0
        self._volume = 10
        self._volatility_ratio = 1.0
        self._market_regime = "NORMAL"
        self._running = False
        self._tick_speed = "NORMAL"
        self._stress_type = None
        self._pending_gap_pct = 0.0
        self._rng = random.Random(42)
        return self.get_control_state()

    def inject_market_stress(self, type: str) -> Dict[str, Any]:
        allowed = {"VOL_SPIKE", "LIQUIDITY_DROP", "GAP", "CRASH", "FLASH_MOVE"}
        if type not in allowed:
            raise ValueError(f"unsupported market stress: {type}")
        self._stress_type = type
        if type == "GAP":
            self._pending_gap_pct = 0.02
        elif type == "CRASH":
            self._pending_gap_pct = -0.05
        elif type == "FLASH_MOVE":
            self._pending_gap_pct = self._rng.choice((-0.03, 0.03))
        return self.get_control_state()

    def clear_market_stress(self) -> Dict[str, Any]:
        self._stress_type = None
        self._pending_gap_pct = 0.0
        return self.get_control_state()

    def set_tick_speed(self, speed: str) -> Dict[str, Any]:
        if speed not in self._SPEED_TO_REPLAY:
            raise ValueError(f"unsupported tick speed: {speed}")
        self._tick_speed = speed
        self.config.replay_speed = self._SPEED_TO_REPLAY[speed]
        return self.get_control_state()

    def get_control_state(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "generator": {
                "base_price": self._initial_price,
                "volatility_ratio": self._volatility_ratio,
                "spread": self.config.base_spread,
                "volume": self._volume,
            },
            "market_regime": self._market_regime,
            "stress": self._stress_type,
            "tick_speed": self._tick_speed,
            "config": self.control.get_config(),
        }

    def _price_delta(self) -> float:
        scale = self._volatility_ratio
        if self._market_regime == "BULL":
            return self._rng.uniform(0.10, 0.60) * scale
        if self._market_regime == "BEAR":
            return self._rng.uniform(-0.60, -0.10) * scale
        if self._market_regime == "SIDEWAYS":
            return self._rng.uniform(-0.25, 0.25) * scale
        if self._market_regime == "VOLATILE":
            return self._rng.uniform(-0.90, 0.90) * scale
        if self._market_regime == "CRISIS":
            return self._rng.uniform(-1.20, 0.30) * scale
        return self._rng.uniform(-0.35, 0.35) * scale

    def _next_market_tick(self) -> CanonicalMarketTick:
        if self._pending_gap_pct:
            self._price = max(100.0, round(self._price * (1.0 + self._pending_gap_pct), 2))
            self._pending_gap_pct = 0.0
        delta = self._price_delta()
        if self._stress_type == "VOL_SPIKE":
            delta *= 3.0
        elif self._stress_type == "FLASH_MOVE":
            delta *= 2.5
        self._price = max(100.0, round(self._price + delta, 2))
        spread = max(0.05, min(1.0, float(self.config.base_spread)))
        if self._stress_type == "LIQUIDITY_DROP":
            spread = min(1.0, spread * 3.0)
        bid = round(self._price - spread / 2.0, 2)
        ask = round(self._price + spread / 2.0, 2)
        volume = self._volume
        if self._stress_type == "LIQUIDITY_DROP":
            volume = max(1, int(volume * 0.25))
        seq = self.state_mgr.next_sequence()
        timestamp = self.clock.get_time_str()
        self.clock.advance_tick(500)
        return CanonicalMarketTick(
            timestamp=timestamp,
            underlying_price=self._price,
            strike_price=round(self._price / 2.5) * 2.5,
            option_type="CALL",
            bid_price=bid,
            ask_price=ask,
            last_price=self._price,
            volume=volume,
            seq_id=seq,
        )

    def step(self) -> Dict[str, Any]:
        tick = self._next_market_tick()
        return {
            "timestamp": tick.timestamp,
            "price": tick.underlying_price,
            "bid": tick.bid_price,
            "ask": tick.ask_price,
            "volume": tick.volume,
            "seq_id": tick.seq_id,
        }

    def generate_tick_stream(self, total_days: int = 1250, ticks_per_day: int = 500) -> Generator[CanonicalMarketTick, None, None]:
        total_ticks = total_days * ticks_per_day
        for _ in range(total_ticks):
            if not self._running:
                return
            yield self._next_market_tick()
'''

TEST_CONTENT = r'''from virtual_market_simulator.runtime.simulator_runtime import VirtualMarketSimulatorRuntime


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
'''

for path in (RUNTIME, TEST):
    if not path.exists():
        raise FileNotFoundError(path)

RUNTIME_BACKUP.write_text(RUNTIME.read_text(encoding="utf-8"), encoding="utf-8")
TEST_BACKUP.write_text(TEST.read_text(encoding="utf-8"), encoding="utf-8")
RUNTIME.write_text(RUNTIME_CONTENT, encoding="utf-8")
TEST.write_text(TEST_CONTENT, encoding="utf-8")

print(f"Applied: {RUNTIME}")
print(f"Backup : {RUNTIME_BACKUP}")
print(f"Applied: {TEST}")
print(f"Backup : {TEST_BACKUP}")