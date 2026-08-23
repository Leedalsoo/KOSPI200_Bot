"""Virtual Securities Firm Control Panel UI Interface."""
import logging
from typing import Dict, Any, Optional
from virtual_securities_firm.account.paper_account import PaperTradingAccount

logger = logging.getLogger(__name__)

class SecuritiesFirmUI:
    """[가상증권사 전용 UI 제어판]"""
    def __init__(self, account: Optional[PaperTradingAccount] = None):
        self.account = account if account is not None else PaperTradingAccount()

    def render_account_dashboard(self) -> Dict[str, Any]:
        summary = self.account.canonical_summary
        return {
            "title": "=== 가상증권사 계좌 및 자산 실시간 제어판 ===",
            "account_id": summary.account_id,
            "total_balance": f"₩{summary.total_balance:,.0f}",
            "used_margin": f"₩{summary.used_margin:,.0f}",
            "free_margin": f"₩{summary.free_margin:,.0f}",
            "realized_pnl": f"₩{summary.realized_pnl:,.0f}",
            "unrealized_pnl": f"₩{summary.unrealized_pnl:,.0f}",
            "status": "OPERATIONAL"
        }

    def render_order_execution_monitor(self, order_history: list) -> Dict[str, Any]:
        return {
            "title": "=== 가상증권사 실시간 체결 모니터 ===",
            "total_orders": len(order_history),
            "recent_orders": order_history[-5:] if order_history else []
        }
