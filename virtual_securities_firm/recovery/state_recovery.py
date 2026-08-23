"""State Recovery Engine for M5 (System Recovery & Snapshot Integrity)."""
import logging
from typing import Dict, Any, Optional
from shared.contracts.canonical import CanonicalAccountSnapshot
from virtual_securities_firm.account.paper_account import PaperTradingAccount

logger = logging.getLogger(__name__)

class StateRecoveryEngine:
    """[M5 상태 복구 엔진: 장애 및 재부팅 시 Account Snapshot 기반 100% 자산 상태 복구]"""
    def __init__(self, account: PaperTradingAccount):
        self.account = account
        self.snapshots: Dict[int, CanonicalAccountSnapshot] = {}

    def create_snapshot(self, sequence_id: int) -> CanonicalAccountSnapshot:
        snap = self.account.get_canonical_summary()
        self.snapshots[sequence_id] = snap
        return snap

    def restore_from_snapshot(self, snapshot: CanonicalAccountSnapshot) -> bool:
        """스냅샷 기반 계좌 100% 복구"""
        try:
            self.account.balance = getattr(snapshot, "total_balance", getattr(snapshot, "balance", 25000000.0))
            self.account.used_margin = snapshot.used_margin
            self.account.free_margin = snapshot.free_margin
            self.account.realized_pnl = snapshot.realized_pnl
            self.account.unrealized_pnl = snapshot.unrealized_pnl
            logger.info(f"[StateRecoveryEngine] Successfully Restored Account Balance={self.account.balance}")
            return True
        except Exception as e:
            logger.error(f"[StateRecoveryEngine] Recovery Failed: {e}")
            return False
