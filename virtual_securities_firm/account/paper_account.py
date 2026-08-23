"""Paper Trading Account - Authoritative Account Mutation & PnL Engine with M5 Domain Delegation."""
import logging
from typing import Dict, Any, List, Optional
from shared.contracts.canonical import CanonicalAccountSummary
from virtual_securities_firm.position.position_manager import PositionManager
from virtual_securities_firm.pnl.pnl_engine import PnLEngine
from virtual_securities_firm.margin.margin_engine import MarginEngine
from virtual_securities_firm.ledger.ledger_engine import LedgerEngine

logger = logging.getLogger(__name__)

class PaperTradingAccount:
    """[VSSF 소유] M5 Authoritative Account & Sub-domain Engine Orchestrator"""
    def __init__(self, initial_capital: float = 25000000.0):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.balance = initial_capital
        self.realized_pnl = 0.0
        self.unrealized_pnl = 0.0
        self.used_margin = 0.0
        self.free_margin = initial_capital
        
        # M5 Sub-domain Engines
        self.position_mgr = PositionManager()
        self.pnl_engine = PnLEngine()
        self.margin_engine = MarginEngine(initial_capital)
        self.ledger_engine = LedgerEngine()

        self.canonical_summary = CanonicalAccountSummary(
            account_id="ACC-VSSF-001",
            total_balance=self.balance,
            used_margin=self.used_margin,
            free_margin=self.free_margin,
            realized_pnl=self.realized_pnl,
            unrealized_pnl=self.unrealized_pnl,
            timestamp="2026-08-23 09:00:00"
        )

    @property
    def positions(self) -> Dict[str, Dict[str, Any]]:
        return self.position_mgr.positions

    @positions.setter
    def positions(self, value: Dict[str, Dict[str, Any]]) -> None:
        self.position_mgr.positions = value

    @property
    def orders_history(self) -> List[Dict[str, Any]]:
        return self.ledger_engine.transactions

    def get_canonical_summary(self) -> CanonicalAccountSummary:
        total_eq = round(self.balance + self.realized_pnl + self.unrealized_pnl, 2)
        self.canonical_summary.total_balance = total_eq
        self.canonical_summary.used_margin = round(self.used_margin, 2)
        self.canonical_summary.free_margin = round(self.free_margin, 2)
        self.canonical_summary.realized_pnl = round(self.realized_pnl, 2)
        self.canonical_summary.unrealized_pnl = round(self.unrealized_pnl, 2)
        self.canonical_summary.positions = {k: dict(v) for k, v in self.position_mgr.positions.items()}
        return self.canonical_summary

    def update_equity(self, current_price: float = 300.0, position_qty: int = 0, portfolio_options: Optional[List[Any]] = None) -> float:
        val = current_price * position_qty * 50000.0
        self.total_equity = self.capital + val
        self.canonical_summary.total_balance = self.total_equity
        return self.canonical_summary.total_balance

    def update_tick_price(self, underlying_price: float) -> float:
        """PnLEngine & MarginEngine에 PnL 및 Margin 계산 위임"""
        self.unrealized_pnl = self.pnl_engine.calculate_unrealized(self.position_mgr.positions, underlying_price)
        total_equity = self.balance + self.realized_pnl + self.unrealized_pnl

        self.used_margin = self.margin_engine.calculate_used_margin(self.position_mgr.positions)
        self.free_margin = self.margin_engine.calculate_free_margin(total_equity, self.used_margin)

        self.canonical_summary.total_balance = total_equity
        self.canonical_summary.unrealized_pnl = self.unrealized_pnl
        self.canonical_summary.used_margin = self.used_margin
        self.canonical_summary.free_margin = self.free_margin
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
        """PositionManager, PnLEngine, MarginEngine, LedgerEngine에 체결 처리 위임"""
        if hasattr(report_or_track_id, "side"):
            rep = report_or_track_id
            effective_track_id = getattr(rep, "track_id", "Track1")
            side_str = rep.side.value if hasattr(rep.side, "value") else str(rep.side)
            exec_qty = rep.executed_qty
            exec_price = rep.executed_price
            exec_fee = rep.fee
            ts = getattr(rep, "timestamp", "2026-08-23 09:00:00")
            exec_id = getattr(rep, "exec_id", "EXEC-001")
            order_id = getattr(rep, "client_order_id", "ORD-001")
            slippage = getattr(rep, "slippage", 0.0)
        else:
            effective_track_id = str(track_id if track_id is not None else report_or_track_id)
            side_str = str(side)
            exec_qty = int(qty) if qty is not None else 1
            exec_price = float(price) if price is not None else 350.0
            exec_fee = float(fee) if fee is not None else 0.0
            ts = "2026-08-23 09:00:00"
            exec_id = "EXEC-001"
            order_id = "ORD-001"
            slippage = 0.0

        pnl_delta = self.position_mgr.update_position(symbol, side_str, exec_qty, exec_price)
        if pnl_delta != 0.0:
            self.pnl_engine.add_realized(pnl_delta)
            self.realized_pnl = self.pnl_engine.realized_pnl

        self.balance -= exec_fee
        self.used_margin = self.margin_engine.calculate_used_margin(self.position_mgr.positions)
        total_equity = self.balance + self.realized_pnl + self.unrealized_pnl
        self.free_margin = self.margin_engine.calculate_free_margin(total_equity, self.used_margin)

        # Ledger Engine 기록
        self.ledger_engine.transactions.append({
            "track_id": effective_track_id,
            "exec_id": exec_id,
            "order_id": order_id,
            "side": side_str,
            "qty": exec_qty,
            "price": exec_price,
            "fee": exec_fee,
            "slippage": slippage,
            "realized_pnl": round(self.realized_pnl, 2),
            "balance_after": round(self.balance, 2),
            "timestamp": ts
        })

        self.canonical_summary.realized_pnl = round(self.realized_pnl, 2)
        self.canonical_summary.total_balance = round(total_equity, 2)
        self.canonical_summary.used_margin = round(self.used_margin, 2)
        self.canonical_summary.free_margin = round(self.free_margin, 2)

    def get_positions(self) -> Dict[str, Dict[str, Any]]:
        return self.position_mgr.positions
