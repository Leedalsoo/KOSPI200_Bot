"""Virtual Securities Firm - Authoritative Paper Trading Account Module."""
import logging
from typing import Dict, Any, List, Optional
from shared.contracts.canonical import CanonicalAccountSummary

logger = logging.getLogger(__name__)

class PaperTradingAccount:
    """[VSSF 소유] 페이퍼 트레이딩(Paper Trading) 모드 가상 계좌 장부"""
    def __init__(self, initial_capital: float = 25000000.0):
        self.capital = initial_capital
        self.reserve = 0.0
        self.total_equity = initial_capital
        self.orders_history: List[Dict[str, Any]] = []
        self.canonical_summary = CanonicalAccountSummary(
            account_id="VIRTUAL-ACCT-01",
            total_balance=initial_capital,
            used_margin=0.0,
            free_margin=initial_capital,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            updated_at=None
        )
        logger.info("Authoritative VSSF Paper Trading Account initialized: ₩%s", f"{initial_capital:,.0f}")

    def update_equity(self, 
                      current_price: float, 
                      position_qty: int, 
                      portfolio_options: List[Dict[str, Any]], 
                      multiplier_futures: float = 50000.0, 
                      multiplier_options: float = 250000.0) -> float:
        """선물 포지션 평가 금액 및 옵션 평가 금액을 종합해 총자산 산출"""
        futures_valuation = position_qty * current_price * multiplier_futures
        options_valuation = sum(
            int(pos.get("qty", 0)) * float(pos.get("price", 0.0)) * multiplier_options
            for pos in portfolio_options
        )
        self.total_equity = self.capital + self.reserve + futures_valuation + options_valuation
        self.canonical_summary.total_balance = self.total_equity
        return self.total_equity
