"""Virtual Market Simulator Runtime with scenario/replay tick supply."""
from __future__ import annotations

import logging
import random
from typing import Any, Dict, Generator, Iterable, Optional

from shared.contracts.canonical import CanonicalMarketTick
from virtual_market_simulator.market.synthetic_market_generator import (
    VirtualBrokerConfig,
    VirtualBrokerControlInterface,
)
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
        self._scenario_step_index = 0

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

    def set_scenario(self, scenario: str) -> Dict[str, Any]:
        self.scenario.set_scenario(scenario)
        return self.get_control_state()

    def load_replay(self, ticks: Iterable[CanonicalMarketTick]) -> Dict[str, Any]:
        self.replay.load(ticks)
        self.replay.reset()
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
        self._scenario_step_index = 0
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
        self._pending_shock_delta = 0.0
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
            "source": "REPLAY" if self.replay.active else "SCENARIO",
            "scenario": self.scenario.state(),
            "replay": {"active": self.replay.active, "cursor": self.replay.cursor, "exhausted": self.replay.exhausted},
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

    def _price_delta(self, scenario_drift: float = 0.0, scenario_volatility: float = 1.0) -> float:
        scale = self._volatility_ratio * scenario_volatility
        if self._market_regime == "BULL":
            delta = self._rng.uniform(0.10, 0.60) * scale
        elif self._market_regime == "BEAR":
            delta = self._rng.uniform(-0.60, -0.10) * scale
        elif self._market_regime == "SIDEWAYS":
            delta = self._rng.uniform(-0.25, 0.25) * scale
        elif self._market_regime == "VOLATILE":
            delta = self._rng.uniform(-0.90, 0.90) * scale
        elif self._market_regime == "CRISIS":
            delta = self._rng.uniform(-1.20, 0.30) * scale
        else:
            delta = self._rng.uniform(-0.35, 0.35) * scale
        return delta + scenario_drift

    def _next_market_tick(self, tick_index: int = 0, ticks_per_day: int = 500) -> CanonicalMarketTick:
        adjustment = self.scenario.next_adjustment(tick_index, ticks_per_day)
        gap_pct = self._pending_gap_pct or adjustment.gap_pct
        if gap_pct:
            self._price = max(100.0, round(self._price * (1.0 + gap_pct), 2))
            self._pending_gap_pct = 0.0
        self._pending_shock_delta = adjustment.shock_delta
        delta = self._price_delta(adjustment.drift, adjustment.volatility_multiplier)
        delta += self._pending_shock_delta
        self._pending_shock_delta = 0.0
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
        if self.replay.active:
            tick = self.replay.next_tick()
            if tick is None:
                raise StopIteration("replay exhausted")
        else:
            tick = self._next_market_tick(self._scenario_step_index, 500)
            self._scenario_step_index += 1
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
        for tick_index in range(total_ticks):
            if not self._running:
                return
            if self.replay.active:
                tick = self.replay.next_tick()
                if tick is None:
                    return
                yield tick
                continue
            yield self._next_market_tick(tick_index, ticks_per_day)