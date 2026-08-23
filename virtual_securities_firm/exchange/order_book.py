"""Virtual Securities Firm - Order Book Module."""
from typing import Dict, Any, List, Optional
from datetime import datetime

class OrderBook:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.bids: List[Dict[str, Any]] = []
        self.asks: List[Dict[str, Any]] = []

    def add_order(self, order: Dict[str, Any]) -> None:
        side = order.get("side", "").upper()
        if side in ("BUY", "BID"):
            self.bids.append(order)
            self.bids.sort(key=lambda x: x.get("price", 0), reverse=True)
        else:
            self.asks.append(order)
            self.asks.sort(key=lambda x: x.get("price", 0))

    def get_best_bid(self) -> Optional[float]:
        return self.bids[0]["price"] if self.bids else None

    def get_best_ask(self) -> Optional[float]:
        return self.asks[0]["price"] if self.asks else None
