"""Position Manager for VSSF M5 Responsibility Decomposition."""
from typing import Dict, Any, Optional


class PositionManager:
    """[M5 포지션 매니저: VSSF 포지션 전담 추적 및 수량/평단가 Mutation 관리]"""

    def __init__(self):
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.order_positions: Dict[str, Dict[str, Any]] = {}

    def _rebuild_aggregate_from_orders(self, symbol: str, side: str) -> None:
        """잔여 order attribution을 기준으로 aggregate position을 재구성한다."""
        lots = [
            pos for pos in self.order_positions.values()
            if pos.get("symbol") == symbol
            and pos.get("side") == side
            and pos.get("qty", 0) > 0
        ]
        if not lots:
            self.positions.pop(symbol, None)
            return

        total_qty = sum(pos["qty"] for pos in lots)
        avg_price = sum(pos["qty"] * pos["avg_price"] for pos in lots) / total_qty
        self.positions[symbol] = {
            "qty": total_qty,
            "avg_price": avg_price,
            "side": side,
        }

    def _reduce_fifo(
        self,
        symbol: str,
        side: str,
        qty: int,
        price: float,
        multiplier: float,
    ) -> tuple[int, float]:
        """동일 Symbol의 반대방향 entry attribution을 FIFO로 차감한다."""
        remaining = qty
        realized_pnl = 0.0

        for order_id, ord_pos in self.order_positions.items():
            if remaining <= 0:
                break
            if (
                ord_pos.get("symbol") != symbol
                or ord_pos.get("side") != side
                or ord_pos.get("qty", 0) <= 0
            ):
                continue

            close_qty = min(ord_pos["qty"], remaining)
            entry_price = ord_pos["avg_price"]
            if side == "BUY":
                realized_pnl += (price - entry_price) * close_qty * multiplier
            else:
                realized_pnl += (entry_price - price) * close_qty * multiplier

            ord_pos["qty"] -= close_qty
            remaining -= close_qty
            self.order_positions[order_id] = ord_pos

        return remaining, realized_pnl

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

        pos = self.positions.get(symbol, {"qty": 0, "avg_price": 0.0, "side": side})
        existing_qty = pos["qty"]
        existing_price = pos["avg_price"]
        existing_side = pos["side"]

        # 신규 진입/동일 방향 증가는 기존 order attribution을 유지한다.
        if existing_qty == 0 or existing_side == side:
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
                else:
                    total_ord_qty = existing_ord_qty + qty
                    ord_pos["avg_price"] = (
                        existing_ord_qty * existing_ord_price + qty * price
                    ) / total_ord_qty
                    ord_pos["qty"] = total_ord_qty
                ord_pos["side"] = side
                ord_pos["symbol"] = symbol
                self.order_positions[client_order_id] = ord_pos

            if existing_qty == 0:
                pos["qty"] = qty
                pos["avg_price"] = price
                pos["side"] = side
            else:
                total_qty = existing_qty + qty
                pos["avg_price"] = (
                    existing_qty * existing_price + qty * price
                ) / total_qty
                pos["qty"] = total_qty
            self.positions[symbol] = pos
            return 0.0

        # 반대 방향 체결: attribution이 존재하면 FIFO로 차감한다.
        has_fifo_lots = any(
            p.get("symbol") == symbol
            and p.get("side") == existing_side
            and p.get("qty", 0) > 0
            for p in self.order_positions.values()
        )

        if has_fifo_lots:
            remaining_qty, realized_pnl = self._reduce_fifo(
                symbol, existing_side, qty, price, multiplier
            )
            self._rebuild_aggregate_from_orders(symbol, existing_side)

            if remaining_qty > 0:
                # 기존 포지션을 모두 청산하고 반대방향 포지션이 남는 경우,
                # 초과분은 신규 entry로 기록한다.
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
                    ord_pos["side"] = side
                    ord_pos["symbol"] = symbol
                    ord_pos["qty"] = ord_pos.get("qty", 0) + remaining_qty
                    ord_pos["avg_price"] = price
                    self.order_positions[client_order_id] = ord_pos

                self.positions[symbol] = {
                    "qty": remaining_qty,
                    "avg_price": price,
                    "side": side,
                }

            return realized_pnl

        # attribution 정보가 없는 기존 호출은 기존 aggregate 감소 동작을 보존한다.
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
