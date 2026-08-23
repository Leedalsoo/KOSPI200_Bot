"""State Recovery Engine for M5 (System Recovery & Snapshot Integrity)."""
import logging
from typing import Dict, Any, Optional
from shared.contracts.canonical import CanonicalAccountSnapshot
from virtual_securities_firm.account.paper_account import PaperTradingAccount

logger = logging.getLogger(__name__)

class StateRecoveryEngine:
    """[M5 상태 복구 엔진: 장애 및 재부팅 시 Account Snapshot 기반 100% 자산 및 포지션 상태 복구]"""
    def __init__(self, account: PaperTradingAccount):
        self.account = account
        self.snapshots: Dict[int, Any] = {}

    def create_snapshot(self, sequence_id: int) -> Dict[str, Any]:
        snap = self.account.get_canonical_summary()
        snapshot_dict = {
            "sequence_id": sequence_id,
            "total_balance": snap.total_balance,
            "used_margin": snap.used_margin,
            "free_margin": snap.free_margin,
            "realized_pnl": snap.realized_pnl,
            "unrealized_pnl": snap.unrealized_pnl,
            "positions": {k: dict(v) for k, v in getattr(snap, "positions", {}).items()},
            "timestamp": snap.timestamp,
        }
        self.snapshots[sequence_id] = snapshot_dict
        return snapshot_dict

    def restore_from_snapshot(self, snapshot: Any) -> bool:
        """스냅샷 기반 계좌 및 포지션 100% 복구"""
        try:
            if isinstance(snapshot, dict):
                bal = snapshot.get("total_balance", snapshot.get("balance", 25000000.0))
                self.account.balance = float(bal)
                self.account.used_margin = float(snapshot.get("used_margin", 0.0))
                self.account.free_margin = float(snapshot.get("free_margin", bal))
                self.account.realized_pnl = float(snapshot.get("realized_pnl", 0.0))
                self.account.unrealized_pnl = float(snapshot.get("unrealized_pnl", 0.0))
                if "positions" in snapshot:
                    self.account.positions = {k: dict(v) for k, v in snapshot["positions"].items()}
            else:
                bal = getattr(snapshot, "total_balance", getattr(snapshot, "balance", 25000000.0))
                self.account.balance = float(bal)
                self.account.used_margin = float(getattr(snapshot, "used_margin", 0.0))
                self.account.free_margin = float(getattr(snapshot, "free_margin", bal))
                self.account.realized_pnl = float(getattr(snapshot, "realized_pnl", 0.0))
                self.account.unrealized_pnl = float(getattr(snapshot, "unrealized_pnl", 0.0))
                if hasattr(snapshot, "positions"):
                    self.account.positions = {k: dict(v) for k, v in snapshot.positions.items()}
            logger.info(f"[StateRecoveryEngine] Successfully Restored Account Balance={self.account.balance}")
            return True
        except Exception as e:
            logger.error(f"[StateRecoveryEngine] Recovery Failed: {e}")
            return False

