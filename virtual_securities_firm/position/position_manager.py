"""Position Manager for VSSF M5 Responsibility Decomposition."""
from typing import Dict, Any, Optional


class PositionManager:
    """[M5 포지션 매니저: VSSF 포지션 전담 추적 및 수량/평단가 Mutation 관리]"""

    def __init__(self):
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.order_positions: Dict[str, Dict[str, Any]] = {}

    def update_position(
        self,
        symbol: str,
        side: str,
        qty: int,
        price: float,
        multiplier: float = 250000.0,
        client_order_id: Optional[str] = None,
    ) -> float:
        """포지션 갱신 및 실현 손익 파생액 반환"""
        if qty <= 0:
            return 0.0

        # 1. 주문별 Position Attribution 갱신
        if client_order_id:
            ord_pos = self.order_positions.get(
                client_order_id,
                {
                    "client_order_id": client_order_id,
                    "symbol": symbol,
                    "side": side,
                    "qty": 0,
                    "avg_price": 0.0,
                },
            )
            existing_ord_qty = ord_pos["qty"]
            existing_ord_price = ord_pos["avg_price"]
            if existing_ord_qty == 0:
                ord_pos["qty"] = qty
                ord_pos["avg_price"] = price
                ord_pos["side"] = side
                ord_pos["symbol"] = symbol
            elif ord_pos["side"] == side:
                tot_qty = existing_ord_qty + qty
                ord_pos["avg_price"] = ((existing_ord_qty * existing_ord_price) + (qty * price)) / tot_qty
                ord_pos["qty"] = tot_qty
            self.order_positions[client_order_id] = ord_pos

        # 2. 계좌 전체 심볼 단위 포지션 갱신 (기존 로직 100% 보존)
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

    def get_order_position(self, client_order_id: str) -> Dict[str, Any]:
        """주문 ID 단위 귀속 포지션 조회"""
        return self.order_positions.get(
            client_order_id,
            {
                "client_order_id": client_order_id,
                "symbol": "",
                "side": "",
                "qty": 0,
                "avg_price": 0.0,
            },
        )

    def get_order_margin(self, client_order_id: str, multiplier: float = 250000.0) -> float:
        """주문 ID 단위 귀속 마진 산출 (수량 x 평단가 x 승수)"""
        ord_pos = self.get_order_position(client_order_id)
        qty = ord_pos.get("qty", 0)
        avg_price = ord_pos.get("avg_price", 0.0)
        return round(qty * avg_price * multiplier, 2)

