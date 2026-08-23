"""Virtual Market Simulator - Synthetic Market Generator Adapter."""
from typing import Dict, Any
from virtual_market_simulator.market.market_clock import MarketClock
from virtual_market_simulator.market.market_state import MarketState

class SyntheticMarketGenerator:
    def __init__(self, clock: MarketClock, state: MarketState):
        self.clock = clock
        self.state = state

    def generate_next_tick(self) -> Dict[str, Any]:
        curr_time = self.clock.tick()
        price = self.state.underlying_price
        return {
            "timestamp": curr_time.isoformat(),
            "underlying_price": price,
            "volatility": self.state.volatility,
            "status": "ACTIVE"
        }
