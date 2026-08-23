"""Ledger Engine for VSSF M5 Responsibility Decomposition."""
from typing import List, Dict, Any
from shared.contracts.canonical import CanonicalExecutionReport

class LedgerEngine:
    """[M5 장부 엔진: VSSF 거래 이력 및 계정 밸런스 변경 트랜잭션 독점 관리]"""
    def __init__(self):
        self.transactions: List[Dict[str, Any]] = []

    def record_execution(self, report: CanonicalExecutionReport, balance: float) -> None:
        self.transactions.append({
            "exec_id": report.exec_id,
            "order_id": report.client_order_id,
            "side": report.side.value if hasattr(report.side, "value") else str(report.side),
            "qty": report.executed_qty,
            "price": report.executed_price,
            "fee": report.fee,
            "slippage": report.slippage,
            "balance_after": balance,
            "timestamp": report.timestamp
        })

    def get_ledger_records(self) -> List[Dict[str, Any]]:
        return list(self.transactions)
