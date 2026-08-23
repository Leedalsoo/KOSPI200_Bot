"""Paper Trading Account - Authoritative Account Mutation & PnL Engine."""
import logging
from typing import Dict, Any, List, Optional
from shared.contracts.canonical import CanonicalAccountSummary

logger = logging.getLogger(__name__)

class PaperTradingAccount:
    """[VSSF 소유] Authoritative Account Mutation & PnL Engine"""
    def __init__(self, initial_capital: float = 25000000.0):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.balance = initial_capital
        self.realized_pnl = 0.0
        self.unrealized_pnl = 0.0
        self.used_margin = 0.0
        self.free_margin = initial_capital
        
        # Positions: symbol -> {"qty": int, "avg_price": float, "side": str}
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.orders_history: List[Dict[str, Any]] = []

        self.canonical_summary = CanonicalAccountSummary(
            account_id="ACC-VSSF-001",
            total_balance=self.balance,
            used_margin=self.used_margin,
            free_margin=self.free_margin,
            realized_pnl=self.realized_pnl,
            unrealized_pnl=self.unrealized_pnl,
            timestamp="2026-08-23 09:00:00"
        )

    def get_canonical_summary(self) -> CanonicalAccountSummary:
        self.canonical_summary.total_balance = round(self.balance + self.realized_pnl + self.unrealized_pnl, 2)
        self.canonical_summary.used_margin = round(self.used_margin, 2)
        self.canonical_summary.free_margin = round(self.free_margin, 2)
        self.canonical_summary.realized_pnl = round(self.realized_pnl, 2)
        self.canonical_summary.unrealized_pnl = round(self.unrealized_pnl, 2)
        return self.canonical_summary

    def update_equity(self, current_price: float = 300.0, position_qty: int = 0, portfolio_options: Optional[List[Any]] = None) -> float:
        val = current_price * position_qty * 50000.0
        self.total_equity = self.capital + val
        self.canonical_summary.total_balance = self.total_equity
        return self.canonical_summary.total_balance

    def update_tick_price(self, underlying_price: float) -> float:
        unrealized = 0.0
        multiplier = 250000.0

        for symbol, pos in list(self.positions.items()):
            qty = pos.get("qty", 0)
            avg_price = pos.get("avg_price", underlying_price)
            side = pos.get("side", "BUY")

            if side == "BUY":
                diff = underlying_price - avg_price
            else:
                diff = avg_price - underlying_price

            unrealized += diff * qty * multiplier

        self.unrealized_pnl = round(unrealized, 2)
        total_equity = self.balance + self.realized_pnl + self.unrealized_pnl

        self.canonical_summary.total_balance = total_equity
        self.canonical_summary.unrealized_pnl = self.unrealized_pnl
        self.canonical_summary.free_margin = max(0.0, total_equity - self.used_margin)
        return total_equity

    def apply_execution(
        self, 
        report_or_track_id: Any = "Track1", 
        side: Optional[str] = None, 
        qty: Optional[int] = None, 
        price: Optional[float] = None, 
        fee: Optional[float] = None, 
        symbol: str = "KOSPI200_OPTION",
        track_id: Optional[str] = None,
        **kwargs
    ) -> None:
        multiplier = 250000.0

        if hasattr(report_or_track_id, "side"):
            rep = report_or_track_id
            effective_track_id = getattr(rep, "track_id", "Track1")
            side_str = rep.side.value if hasattr(rep.side, "value") else str(rep.side)
            exec_qty = rep.executed_qty
            exec_price = rep.executed_price
            exec_fee = rep.fee
        else:
            effective_track_id = str(track_id if track_id is not None else report_or_track_id)
            side_str = str(side)
            exec_qty = int(qty) if qty is not None else 1
            exec_price = float(price) if price is not None else 350.0
            exec_fee = float(fee) if fee is not None else 0.0

        pos = self.positions.get(symbol, {"qty": 0, "avg_price": 0.0, "side": side_str})
        existing_qty = pos["qty"]
        existing_price = pos["avg_price"]
        existing_side = pos["side"]

        if existing_qty == 0:
            pos["qty"] = exec_qty
            pos["avg_price"] = exec_price
            pos["side"] = side_str
            self.positions[symbol] = pos
        elif existing_side == side_str:
            total_qty = existing_qty + exec_qty
            pos["avg_price"] = ((existing_qty * existing_price) + (exec_qty * exec_price)) / total_qty
            pos["qty"] = total_qty
            self.positions[symbol] = pos
        else:
            close_qty = min(existing_qty, exec_qty)
            if existing_side == "BUY":
                trade_pnl = (exec_price - existing_price) * close_qty * multiplier - exec_fee
            else:
                trade_pnl = (existing_price - exec_price) * close_qty * multiplier - exec_fee

            self.realized_pnl += trade_pnl
            remaining_qty = existing_qty - close_qty

            if remaining_qty > 0:
                pos["qty"] = remaining_qty
                self.positions[symbol] = pos
            else:
                new_qty = exec_qty - close_qty
                if new_qty > 0:
                    pos["qty"] = new_qty
                    pos["avg_price"] = exec_price
                    pos["side"] = side_str
                    self.positions[symbol] = pos
                else:
                    self.positions.pop(symbol, None)

        active_margin = 0.0
        for pos_item in self.positions.values():
            active_margin += pos_item["avg_price"] * pos_item["qty"] * multiplier
        self.used_margin = round(active_margin, 2)

        self.balance -= exec_fee

        self.canonical_summary.realized_pnl = round(self.realized_pnl, 2)
        total_equity = self.balance + self.realized_pnl + self.unrealized_pnl
        self.canonical_summary.total_balance = round(total_equity, 2)
        self.canonical_summary.used_margin = round(self.used_margin, 2)
        self.canonical_summary.free_margin = max(0.0, total_equity - self.used_margin)

        self.orders_history.append({
            "track_id": effective_track_id,
            "side": side_str,
            "qty": exec_qty,
            "price": exec_price,
            "fee": exec_fee,
            "realized_pnl": round(self.realized_pnl, 2)
        })

    def get_positions(self) -> Dict[str, Dict[str, Any]]:
        return self.positions
