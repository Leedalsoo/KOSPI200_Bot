"""Virtual Securities Firm - Authoritative ExecutionReport Factory."""
import uuid
from datetime import datetime
from typing import Dict, Any
from shared.contracts.canonical import CanonicalExecutionReport

class ExecutionReportFactory:
    @staticmethod
    def create_report(
        order_id: str,
        symbol: str,
        side: str,
        price: float,
        quantity: int,
        fee: float = 0.0,
        slippage: float = 0.0,
        metadata: Dict[str, Any] = None
    ) -> CanonicalExecutionReport:
        exec_id = f"EXEC-{uuid.uuid4().hex[:8].upper()}"
        return CanonicalExecutionReport(
            execution_id=exec_id,
            order_id=order_id,
            symbol=symbol,
            side=side,
            price=price,
            quantity=quantity,
            executed_at=datetime.now(),
            fee=fee,
            slippage=slippage,
            metadata=metadata or {}
        )
