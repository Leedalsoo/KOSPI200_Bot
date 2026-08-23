"""Virtual Market Simulator - Market State Module."""
from dataclasses import dataclass, field
from typing import Dict, Any, Optional

@dataclass
class MarketState:
    underlying_price: float = 360.0
    volatility: float = 0.15
    regime: str = "NORMAL"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def update_price(self, new_price: float) -> None:
        self.underlying_price = new_price

    def update_volatility(self, new_vol: float) -> None:
        self.volatility = new_vol
