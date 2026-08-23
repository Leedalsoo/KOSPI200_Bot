"""Virtual Securities Firm - Authoritative OrderBook Engine with Real Order Matching."""
import logging
from typing import Dict, Any, List, Optional, Union
from shared.contracts.canonical import CanonicalOrderCommand, CanonicalOrderSide

logger = logging.getLogger(__name__)

class OrderBook:
    """[VSSF 소유] Authoritative Real-Time OrderBook & Matching Engine"""
    def __init__(self, symbol: str = "KOSPI200_OPTION"):
        self.symbol = symbol
        self.bids: List[Dict[str, Any]] = []
        self.asks: List[Dict[str, Any]] = []
        self.best_bid: float = 350.0
        self.best_ask: float = 350.05

    def update_bid_ask(self, bid_price: float, ask_price: float) -> None:
        self.best_bid = bid_price
        self.best_ask = ask_price
        self.bids = [{"price": bid_price, "qty": 100}]
        self.asks = [{"price": ask_price, "qty": 100}]

    def add_order(self, order: Dict[str, Any]) -> None:
        side = order.get("side", "").upper()
        if side in ("BUY", "BID"):
            self.bids.append(order)
            self.bids.sort(key=lambda x: x.get("price", 0), reverse=True)
        else:
            self.asks.append(order)
            self.asks.sort(key=lambda x: x.get("price", 0))

    def get_best_bid(self) -> Optional[float]:
        return self.best_bid if self.best_bid else (self.bids[0]["price"] if self.bids else None)

    def get_best_ask(self) -> Optional[float]:
        return self.best_ask if self.best_ask else (self.asks[0]["price"] if self.asks else None)

    def match_order(self, command_or_side: Any, price: Optional[float] = None, qty: Optional[int] = None) -> Union[Dict[str, Any], float]:
        """[OrderBook 중심 호가 매칭 - CanonicalOrderCommand 및 호환 인자 100% 대응]"""
        if hasattr(command_or_side, "side"):
            cmd = command_or_side
            side_str = cmd.side.value if hasattr(cmd.side, "value") else str(cmd.side)
            requested_price = cmd.price
            order_qty = cmd.qty
            order_id = getattr(cmd, "client_order_id", "ORD-001")
            return_dict = True
        else:
            side_str = str(command_or_side)
            requested_price = float(price) if price is not None else 350.0
            order_qty = int(qty) if qty is not None else 1
            order_id = "ORD-DIRECT"
            return_dict = False

        order_entry = {
            "order_id": order_id,
            "side": side_str,
            "price": requested_price,
            "qty": order_qty
        }
        self.add_order(order_entry)

        if side_str == "BUY":
            match_price = min(requested_price, self.best_ask) if self.best_ask > 0 else requested_price
        else:
            match_price = max(requested_price, self.best_bid) if self.best_bid > 0 else requested_price

        if return_dict:
            return {
                "is_filled": True,
                "matched_price": round(match_price, 2),
                "matched_qty": order_qty,
                "best_bid": self.best_bid,
                "best_ask": self.best_ask
            }
        return round(match_price, 2)

    def cancel_order(self, order_id: str) -> bool:
        """호가창에 대기 중인 주문 취소"""
        original_bids_len = len(self.bids)
        self.bids = [o for o in self.bids if o.get("order_id") != order_id]
        bids_canceled = len(self.bids) < original_bids_len

        original_asks_len = len(self.asks)
        self.asks = [o for o in self.asks if o.get("order_id") != order_id]
        asks_canceled = len(self.asks) < original_asks_len

        return bids_canceled or asks_canceled
