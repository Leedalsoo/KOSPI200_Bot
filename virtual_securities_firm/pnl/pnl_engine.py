"""PnL Engine for VSSF M5 Responsibility Decomposition."""
from typing import Dict, Any

class PnLEngine:
    """[M5 PnL 엔진: Mark-to-Market 미실현 손익 및 실현 손익 독점 전담]"""
    def __init__(self):
        self.realized_pnl: float = 0.0
        self.unrealized_pnl: float = 0.0

    def calculate_unrealized(self, positions: Dict[str, Dict[str, Any]], current_price: float, multiplier: float = 250000.0) -> float:
        unrealized = 0.0
        for symbol, pos in positions.items():
            qty = pos.get("qty", 0)
            avg_price = pos.get("avg_price", current_price)
            side = pos.get("side", "BUY")

            if side == "BUY":
                diff = current_price - avg_price
            else:
                diff = avg_price - current_price

            unrealized += diff * qty * multiplier

        self.unrealized_pnl = round(unrealized, 2)
        return self.unrealized_pnl

    def add_realized(self, amount: float) -> float:
        self.realized_pnl += amount
        return self.realized_pnl
