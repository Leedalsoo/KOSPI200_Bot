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
            timestamp="2026-08-23 09:00:00"
        )
        logger.info("Authoritative VSSF Paper Trading Account initialized: KRW %s", f"{initial_capital:,.0f}")

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

    def update_tick_price(self, price: float) -> float:
        """틱 시세에 따라 가상 계좌 평가 갱신"""
        self.canonical_summary.free_margin = self.canonical_summary.total_balance
        return self.canonical_summary.total_balance

    def apply_execution(self, track_id: str, side: str, qty: int, price: float, fee: float) -> None:
        """체결 내역 장부 반영"""
        cost = price * qty * 250000 + fee
        if side == "BUY":
            self.canonical_summary.used_margin += cost
            self.canonical_summary.free_margin = max(0.0, self.canonical_summary.total_balance - self.canonical_summary.used_margin)
        self.orders_history.append({"track_id": track_id, "side": side, "qty": qty, "price": price, "fee": fee})

