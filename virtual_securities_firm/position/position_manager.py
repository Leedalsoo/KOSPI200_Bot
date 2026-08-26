"""Position Manager for VSSF M5 Responsibility Decomposition."""
from typing import Dict, Any, List

class PositionManager:
    """[M5 포지션 매니저: VSSF 포지션 전담 추적 및 수량/평단가 Mutation 관리]"""
    def __init__(self):
        self.positions: Dict[str, Dict[str, Any]] = {}

    def update_position(self, symbol: str, side: str, qty: int, price: float, multiplier: float = 250000.0) -> float:
        """포지션 갱신 및 실현 손익 파생액 반환"""
        if qty <= 0:
            return 0.0

        pos = self.positions.get(symbol, {"qty": 0, "avg_price": 0.0, "side": side})
        existing_qty = pos["qty"]
        existing_price = pos["avg_price"]
        existing_side = pos["side"]

        realized_pnl = 0.0

        if existing_qty == 0:
            pos["qty"] = qty
            pos["avg_price"] = price
            pos["side"] = side
            self.positions[symbol] = pos
        elif existing_side == side:
            total_qty = existing_qty + qty
            pos["avg_price"] = ((existing_qty * existing_price) + (qty * price)) / total_qty
            pos["qty"] = total_qty
            self.positions[symbol] = pos
        else:
            close_qty = min(existing_qty, qty)
            if existing_side == "BUY":
                realized_pnl = (price - existing_price) * close_qty * multiplier
            else:
                realized_pnl = (existing_price - price) * close_qty * multiplier

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

        return realized_pnl
