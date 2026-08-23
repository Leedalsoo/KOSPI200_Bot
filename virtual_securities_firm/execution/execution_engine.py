"""Virtual Securities Firm - Authoritative Execution Engine."""
from typing import Dict, Any, Optional
from shared.contracts.canonical import CanonicalExecutionReport, CanonicalOrderCommand
from virtual_securities_firm.execution.execution_report_factory import ExecutionReportFactory

class ExecutionEngine:
    def __init__(self):
        self.reports = []

    def execute_order(self, order: CanonicalOrderCommand, fill_price: Optional[float] = None) -> CanonicalExecutionReport:
        price = fill_price if fill_price is not None else order.price
        report = ExecutionReportFactory.create_report(
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            price=price,
            quantity=order.quantity,
            fee=0.0,
            slippage=0.0,
            metadata=order.metadata
        )
        self.reports.append(report)
        return report
