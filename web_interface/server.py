"""Target Architecture UI Backend API Server."""
import asyncio
import logging
from typing import Any, Dict, Optional, Set

import orjson

logger = logging.getLogger(__name__)


class TargetArchitectureUIServer:
    """TradingSystem 상태를 UI 전용 DTO로 변환하는 Adapter."""

    def __init__(self, trading_system=None):
        self.system = trading_system

    def attach_runtime(self, trading_system) -> None:
        self.system = trading_system

    @staticmethod
    def _build_pnl_coord(tick: Any, account: Any) -> Dict[str, float]:
        """현재 틱과 권위 계좌 스냅샷에서 Realtime PnL 차트용 단일 좌표를 생성."""
        seq_id = int(getattr(tick, "seq_id", 0) or 0) if tick is not None else 0
        realized = float(getattr(account, "realized_pnl", 0.0) or 0.0)
        unrealized = float(getattr(account, "unrealized_pnl", 0.0) or 0.0)
        return {"x": seq_id, "y": realized + unrealized}

    def snapshot(self) -> Dict[str, Any]:
        if self.system is None:
            return {"type": "ui_snapshot", "status": "NO_RUNTIME"}

        tick = self.system.last_tick
        condition = self.system.op_runtime.market_condition
        account = self.system.vssf.get_account_snapshot()
        risk = self.system.op_runtime.last_risk_snapshot
        reports = self.system.op_runtime.received_execution_reports[-20:]
        metrics = self.system.op_runtime.strategy_metrics

        return {
            "type": "ui_snapshot",
            "market": {
                "timestamp": tick.timestamp if tick else "",
                "seq_id": tick.seq_id if tick else 0,
                "price": tick.underlying_price if tick else 0.0,
                "bid": tick.bid_price if tick else 0.0,
                "ask": tick.ask_price if tick else 0.0,
                "spread": (tick.ask_price - tick.bid_price) if tick else 0.0,
                "volume": tick.volume if tick else 0,
            },
            "marketCondition": condition.to_dict() if condition else {},
            "broker": {
                "mode": self.system.broker_mode,
                "account": {
                    "balance": account.total_balance,
                    "realized_pnl": account.realized_pnl,
                    "unrealized_pnl": account.unrealized_pnl,
                    "used_margin": account.used_margin,
                    "free_margin": account.free_margin,
                },
            },
            "optionProgram": {
                "current_regime": self.system.op_runtime.current_regime,
                "strategy_metrics": metrics,
                "enabled_strategies": self.system.op_runtime.enabled_strategies,
            },
            "strategies": metrics,
            "positions": account.positions,
            "orders": self.system.op_runtime.last_orders[-20:],
            "executions": [
                {
                    "exec_id": r.exec_id,
                    "client_order_id": r.client_order_id,
                    "track_id": r.track_id,
                    "asset_type": r.asset_type.value,
                    "side": r.side.value,
                    "executed_qty": r.executed_qty,
                    "executed_price": r.executed_price,
                    "fee": r.fee,
                    "slippage": r.slippage,
                    "timestamp": r.timestamp,
                }
                for r in reports
            ],
            "pnl": {
                "realized": account.realized_pnl,
                "unrealized": account.unrealized_pnl,
                "total": account.realized_pnl + account.unrealized_pnl,
            },
            "coord": self._build_pnl_coord(tick, account),
            "risk": risk.__dict__ if risk else {},
            "payoff": self._build_payoff(account.positions, tick.underlying_price if tick else 350.0),
            "replay": {
                "timestamp": tick.timestamp if tick else "",
                "ticks_processed": self.system.ticks_processed,
                "orders_routed": self.system.orders_routed,
                "executions_handled": self.system.executions_handled,
            },
        }

    @staticmethod
    def _build_payoff(positions: Dict[str, Any], current_price: float):
        points = []
        if not positions:
            return points
        for i in range(-20, 21):
            x = current_price + i
            pnl = 0.0
            for value in positions.values():
                if not isinstance(value, dict):
                    continue
                qty = float(value.get("qty", 0))
                entry = float(value.get("avg_price", value.get("price", current_price)))
                side = str(value.get("side", "BUY")).upper()
                sign = 1.0 if side == "BUY" else -1.0
                pnl += (x - entry) * qty * sign
            points.append({"x": x, "y": pnl})
        return points

    async def handle_command(self, command: Dict[str, Any]) -> None:
        if self.system is None:
            return
        if command.get("action") == "set_strategy_enabled":
            track_id = str(command.get("track_id", ""))
            enabled = bool(command.get("enabled", True))
            self.system.op_runtime.set_strategy_enabled(track_id, enabled)


class UIWebSocketHub:
    """실제 TradingSystem 상태를 하나의 WebSocket 경로로 fan-out."""

    def __init__(self, adapter: TargetArchitectureUIServer, host: str = "127.0.0.1", port: int = 8765):
        self.adapter = adapter
        self.host = host
        self.port = port
        self.clients: Set[Any] = set()
        self.server = None

    async def handler(self, websocket):
        self.clients.add(websocket)
        try:
            await websocket.send(orjson.dumps(self.adapter.snapshot()).decode("utf-8"))
            async for message in websocket:
                try:
                    command = orjson.loads(message)
                    await self.adapter.handle_command(command)
                    await websocket.send(orjson.dumps(self.adapter.snapshot()).decode("utf-8"))
                except Exception as exc:
                    logger.warning("UI command failed: %s", exc)
        finally:
            self.clients.discard(websocket)

    async def start(self):
        from websockets.server import serve
        self.server = await serve(self.handler, self.host, self.port)
        logger.info("UI WebSocket server listening on ws://%s:%s", self.host, self.port)

    async def broadcast(self):
        if not self.clients:
            return
        payload = orjson.dumps(self.adapter.snapshot()).decode("utf-8")
        dead = []
        for client in list(self.clients):
            try:
                await client.send(payload)
            except Exception:
                dead.append(client)
        for client in dead:
            self.clients.discard(client)

    async def stop(self):
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
        self.clients.clear()
