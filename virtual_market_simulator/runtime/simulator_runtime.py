"""Virtual Market Simulator Runtime - market data generation only."""
import logging
import random
from typing import Generator, Optional, Dict, Any

from shared.contracts.canonical import CanonicalMarketTick
from virtual_market_simulator.market.synthetic_market_generator import (
    VirtualBrokerConfig,
    VirtualBrokerControlInterface,
)
from virtual_market_simulator.engine.clock_controller import VMSClockController
from virtual_market_simulator.engine.vms_state_manager import VMSStateManager

logger = logging.getLogger(__name__)


class VirtualMarketSimulatorRuntime:
    """Production VMS: 시장 데이터를 생성/공급한다. 상황판단과 강제 시나리오 주입은 담당하지 않는다."""

    def __init__(self, config: Optional[VirtualBrokerConfig] = None) -> None:
        self.config = config or VirtualBrokerConfig()
        self.control = VirtualBrokerControlInterface(config=self.config)
        self.clock = VMSClockController()
        self.state_mgr = VMSStateManager()
        self._price = 350.0
        self._rng = random.Random(42)

    def _next_market_tick(self) -> CanonicalMarketTick:
        self._price = max(100.0, round(self._price + self._rng.uniform(-0.35, 0.35), 2))
        spread = max(0.05, min(1.0, self.config.base_spread))
        bid = round(self._price - spread / 2.0, 2)
        ask = round(self._price + spread / 2.0, 2)
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
            volume=10,
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

    def generate_tick_stream(
        self,
        total_days: int = 1250,
        ticks_per_day: int = 500,
    ) -> Generator[CanonicalMarketTick, None, None]:
        total_ticks = total_days * ticks_per_day
        for _ in range(total_ticks):
            yield self._next_market_tick()

