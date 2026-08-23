"""State Recovery Engine for M5 (System Recovery & Snapshot Integrity)."""
import logging
from typing import Dict, Any, Optional
from shared.contracts.canonical import CanonicalAccountSnapshot
from virtual_securities_firm.account.paper_account import PaperTradingAccount

logger = logging.getLogger(__name__)

class StateRecoveryEngine:
    """[M5 전체 런타임 상태 복구 엔진: Account, Position, Ledger, Metrics 등 100% 완전 상태 복구]"""
    def __init__(self, account: PaperTradingAccount):
        self.account = account
        self.snapshots: Dict[int, Any] = {}

    def create_snapshot(self, sequence_id: int, metrics: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        snap = self.account.get_canonical_summary()
        ledger_txs = list(getattr(self.account.ledger_engine, "transactions", []))
        snapshot_dict = {
            "sequence_id": sequence_id,
            "total_balance": snap.total_balance,
            "balance": self.account.balance,
            "used_margin": snap.used_margin,
            "free_margin": snap.free_margin,
            "realized_pnl": snap.realized_pnl,
            "unrealized_pnl": snap.unrealized_pnl,
            "positions": {k: dict(v) for k, v in getattr(snap, "positions", {}).items()},
            "ledger_transactions": [dict(tx) for tx in ledger_txs],
            "metrics": dict(metrics) if metrics is not None else {},
            "timestamp": snap.timestamp,
        }
        self.snapshots[sequence_id] = snapshot_dict
        return snapshot_dict

    def restore_from_snapshot(self, snapshot: Any, target_metrics: Optional[Dict[str, Any]] = None) -> bool:
        """스냅샷 기반 계좌, 포지션, 원장(Ledger) 전체 상태 100% 복구"""
        try:
            if isinstance(snapshot, dict):
                bal = snapshot.get("balance", snapshot.get("total_balance", 25000000.0))
                self.account.balance = float(bal)
                self.account.used_margin = float(snapshot.get("used_margin", 0.0))
                self.account.free_margin = float(snapshot.get("free_margin", bal))
                self.account.realized_pnl = float(snapshot.get("realized_pnl", 0.0))
                self.account.unrealized_pnl = float(snapshot.get("unrealized_pnl", 0.0))
                if "positions" in snapshot:
                    self.account.positions = {k: dict(v) for k, v in snapshot["positions"].items()}
                if "ledger_transactions" in snapshot:
                    self.account.ledger_engine.transactions = [dict(tx) for tx in snapshot["ledger_transactions"]]
                if target_metrics is not None and "metrics" in snapshot:
                    target_metrics.update(snapshot["metrics"])
            else:
                bal = getattr(snapshot, "balance", getattr(snapshot, "total_balance", 25000000.0))
                self.account.balance = float(bal)
                self.account.used_margin = float(getattr(snapshot, "used_margin", 0.0))
                self.account.free_margin = float(getattr(snapshot, "free_margin", bal))
                self.account.realized_pnl = float(getattr(snapshot, "realized_pnl", 0.0))
                self.account.unrealized_pnl = float(getattr(snapshot, "unrealized_pnl", 0.0))
                if hasattr(snapshot, "positions"):
                    self.account.positions = {k: dict(v) for k, v in snapshot.positions.items()}
                if hasattr(snapshot, "ledger_transactions"):
                    self.account.ledger_engine.transactions = [dict(tx) for tx in snapshot.ledger_transactions]
                if target_metrics is not None and hasattr(snapshot, "metrics"):
                    target_metrics.update(getattr(snapshot, "metrics", {}))
            logger.info(f"[StateRecoveryEngine] Successfully Restored Full Runtime State: Balance={self.account.balance}, Positions={len(self.account.positions)}, LedgerEntries={len(self.account.ledger_engine.transactions)}")
            return True

        except Exception as e:
            logger.error(f"[StateRecoveryEngine] Recovery Failed: {e}")
            return False


