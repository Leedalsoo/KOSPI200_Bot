"""Paper Trading Account - Authoritative Account Mutation & PnL Engine."""
import logging
from typing import Dict, Any, List, Optional
from shared.contracts.canonical import CanonicalAccountSummary

logger = logging.getLogger(__name__)

class PaperTradingAccount:
    """[VSSF 소유] Authoritative Account Mutation & PnL Engine"""
    def __init__(self, initial_capital: float = 25000000.0):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.balance = initial_capital
        self.realized_pnl = 0.0
        self.unrealized_pnl = 0.0
        self.used_margin = 0.0
        self.free_margin = initial_capital
        
        # Positions: symbol -> {"qty": int, "avg_price": float, "side": str}
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.orders_history: List[Dict[str, Any]] = []

        self.canonical_summary = CanonicalAccountSummary(
            account_id="ACC-VSSF-001",
            total_balance=self.balance,
            used_margin=self.used_margin,
            free_margin=self.free_margin,
            realized_pnl=self.realized_pnl,
            unrealized_pnl=self.unrealized_pnl,
            timestamp="2026-08-23 09:00:00"
        )

    def update_equity(self, current_price: float = 300.0, position_qty: int = 0, portfolio_options: Optional[List[Any]] = None) -> float:
        """이전 테스트 호환용 update_equity 메서드"""
        val = current_price * position_qty * 50000.0
        self.total_equity = self.capital + val
        self.canonical_summary.total_balance = self.total_equity
        return self.canonical_summary.total_balance

    def update_tick_price(self, underlying_price: float) -> float:
        """[VSSF 마켓 시세 반영: 미실현 PnL (Unrealized PnL) 및 자산 재평가 Mutation]"""
        unrealized = 0.0
        multiplier = 250000.0  # KOSPI200 파생 승수

        for symbol, pos in list(self.positions.items()):
            qty = pos.get("qty", 0)
            avg_price = pos.get("avg_price", underlying_price)
            side = pos.get("side", "BUY")

            # Option Mark-to-Market Valuation based on Option Premium Price
            if side == "BUY":
                diff = underlying_price - avg_price
            else:
                diff = avg_price - underlying_price

            unrealized += diff * qty * multiplier

        self.unrealized_pnl = round(unrealized, 2)
        total_equity = self.balance + self.realized_pnl + self.unrealized_pnl

        # Update Canonical Summary
        self.canonical_summary.total_balance = total_equity
        self.canonical_summary.unrealized_pnl = self.unrealized_pnl
        self.canonical_summary.free_margin = max(0.0, total_equity - self.used_margin)
        return total_equity

    def apply_execution(self, track_id: str, side: str, qty: int, price: float, fee: float, symbol: str = "KOSPI200_OPTION") -> None:
        """[VSSF 체결 이행 ➔ 포지션/증거금/실현 PnL (Realized PnL) Account Mutation]"""
        multiplier = 250000.0

        pos = self.positions.get(symbol, {"qty": 0, "avg_price": 0.0, "side": side})
        existing_qty = pos["qty"]
        existing_price = pos["avg_price"]
        existing_side = pos["side"]

        if existing_qty == 0:
            # 신규 포지션 오픈
            pos["qty"] = qty
            pos["avg_price"] = price
            pos["side"] = side
            self.positions[symbol] = pos
        elif existing_side == side:
            # 동일 방향 포지션 추가
            total_qty = existing_qty + qty
            pos["avg_price"] = ((existing_qty * existing_price) + (qty * price)) / total_qty
            pos["qty"] = total_qty
            self.positions[symbol] = pos
        else:
            # 반대 방향 청산 / 청산 실현 손익 (Realized PnL) 계산
            close_qty = min(existing_qty, qty)
            if existing_side == "BUY":
                trade_pnl = (price - existing_price) * close_qty * multiplier - fee
            else:
                trade_pnl = (existing_price - price) * close_qty * multiplier - fee

            self.realized_pnl += trade_pnl
            remaining_qty = existing_qty - close_qty

            if remaining_qty > 0:
                pos["qty"] = remaining_qty
                self.positions[symbol] = pos
            else:
                new_qty = qty - close_qty
                if new_qty > 0:
                    pos["qty"] = new_qty
                    pos["avg_price"] = price
                    pos["side"] = side
                    self.positions[symbol] = pos
                else:
                    self.positions.pop(symbol, None)

        # Recalculate authoritative used margin based on active open positions
        active_margin = 0.0
        for pos_item in self.positions.values():
            active_margin += pos_item["avg_price"] * pos_item["qty"] * multiplier
        self.used_margin = round(active_margin, 2)

        # Deduct transaction fee from cash balance
        self.balance -= fee

        # Update balance and canonical summary
        self.canonical_summary.realized_pnl = round(self.realized_pnl, 2)
        total_equity = self.balance + self.realized_pnl + self.unrealized_pnl
        self.canonical_summary.total_balance = round(total_equity, 2)
        self.canonical_summary.used_margin = round(self.used_margin, 2)
        self.canonical_summary.free_margin = max(0.0, total_equity - self.used_margin)

        self.orders_history.append({
            "track_id": track_id,
            "side": side,
            "qty": qty,
            "price": price,
            "fee": fee,
            "realized_pnl": round(self.realized_pnl, 2)
        })

    def get_positions(self) -> Dict[str, Dict[str, Any]]:
        return self.positions
