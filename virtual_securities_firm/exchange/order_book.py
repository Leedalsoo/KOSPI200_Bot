"""Virtual Securities Firm - Authoritative KRX Order Book Module."""
import random
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import Tuple, Optional, Dict, Any, List
import logging

logger = logging.getLogger(__name__)

OPTION_TICK_TABLE: List[Tuple[Decimal, Decimal]] = [
    (Decimal("3.00"),     Decimal("0.01")),
    (Decimal("9999.99"), Decimal("0.05")),
]

def get_option_tick_size(price: float) -> Decimal:
    d_price = Decimal(str(round(price, 4)))
    for threshold, tick_size in OPTION_TICK_TABLE:
        if d_price < threshold:
            return tick_size
    return Decimal("0.05")

def snap_to_tick(price: float, side: str = "BUY") -> float:
    d_price = Decimal(str(round(price, 4)))
    tick = get_option_tick_size(price)
    if side.upper() in ("BUY", "BID"):
        snapped = (d_price / tick).quantize(Decimal("1"), rounding=ROUND_DOWN) * tick
    else:
        snapped = (d_price / tick).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * tick
    return float(snapped)


class OrderBook:
    """[VSSF 소유] Authoritative OrderBook Engine"""
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

    def update_bid_ask(self, bid_price: float, ask_price: float) -> None:
        self.bids = [{"price": bid_price, "qty": 10}]
        self.asks = [{"price": ask_price, "qty": 10}]
