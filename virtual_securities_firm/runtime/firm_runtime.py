"""Virtual Securities Firm Runtime Entrypoint."""
from typing import Dict, Any, List, Optional
from shared.contracts.canonical import (
    CanonicalOrderCommand,
    CanonicalExecutionReport,
    CanonicalPositionSnapshot,
    CanonicalAccountSummary
)
from virtual_securities_firm.exchange.order_book import OrderBook
from virtual_securities_firm.execution.execution_engine import ExecutionEngine

class VirtualSecuritiesFirmRuntime:
    def __init__(self, symbol: str = "KOSPI200_OPT"):
        self.symbol = symbol
        self.order_book = OrderBook(symbol)
        self.execution_engine = ExecutionEngine()
        self.positions: Dict[str, CanonicalPositionSnapshot] = {}
        self.account = CanonicalAccountSummary(
            account_id="VIRTUAL-ACCT-01",
            total_balance=100000000.0,
            used_margin=0.0,
            free_margin=100000000.0,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            updated_at=None
        )

    def submit_order(self, order: CanonicalOrderCommand) -> CanonicalExecutionReport:
        report = self.execution_engine.execute_order(order)
        return report

    def get_account_summary(self) -> CanonicalAccountSummary:
        return self.account
