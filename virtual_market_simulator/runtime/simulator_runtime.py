"""Virtual Market Simulator Integration Entrypoint."""
from typing import Dict, Any, Optional
from virtual_market_simulator.market.synthetic_market_generator import SyntheticMarketGenerator
from virtual_market_simulator.market.market_clock import MarketClock
from virtual_market_simulator.market.market_state import MarketState

class VirtualMarketSimulatorRuntime:
    def __init__(self, time_scale: float = 1.0):
        self.clock = MarketClock(time_scale=time_scale)
        self.state = MarketState()
        self.generator = SyntheticMarketGenerator(self.clock, self.state)

    def next_tick(self) -> Dict[str, Any]:
        return self.generator.generate_next_tick()

    def set_underlying_price(self, price: float) -> None:
        self.state.update_price(price)
