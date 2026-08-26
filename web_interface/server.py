"""Target Architecture UI Backend API Server."""
import inspect
import logging
import time
from typing import Any, Dict, Set

import orjson

logger = logging.getLogger(__name__)


class UICommandError(ValueError):
    """UI Command validation/dispatch error."""


class TargetArchitectureUIServer:
    """TradingSystem 상태 Adapter 및 UI Command Dispatcher."""

    _COMMAND_SPECS = {
        "set_strategy_enabled": ("op_runtime", "set_strategy_enabled", {"track_id": str, "enabled": bool}, {}),
        "set_margin_mode": ("vssf", "set_margin_mode", {"mode": str}, {"mode": {"NORMAL", "TIGHT"}}),
        "inject_margin_call": ("vssf", "inject_margin_call", {}, {}),
        "inject_margin_shortage": ("vssf", "inject_margin_shortage", {}, {}),
        "set_leverage": ("vssf", "set_leverage", {"leverage": (int, float)}, {}),
        "set_broker_connection": ("broker", "set_connection", {"connected": bool}, {}),
        "set_broker_latency": ("broker", "set_latency", {"latency_ms": (int, float)}, {}),
        "set_execution_behavior": ("broker", "set_execution_behavior", {"mode": str}, {"mode": {"NORMAL", "DELAYED", "REJECT"}}),
        "set_market_generator": ("vms", "set_generator_config", {"base_price": (int, float), "volatility_ratio": (int, float), "spread": (int, float), "volume": (int, float)}, {}),
        "set_market_regime": ("vms", "set_market_regime", {"regime": str}, {"regime": {"NORMAL", "BULL", "BEAR", "SIDEWAYS", "VOLATILE", "CRISIS"}}),
        "set_simulation_runtime": ("vms", "set_running", {"running": bool}, {}),
        "reset_market_simulation": ("vms", "reset_simulation", {}, {}),
        "inject_market_stress": ("vms", "inject_market_stress", {"type": str}, {"type": {"VOL_SPIKE", "LIQUIDITY_DROP", "GAP", "CRASH", "FLASH_MOVE"}}),
        "clear_market_stress": ("vms", "clear_market_stress", {}, {}),
        "set_tick_speed": ("vms", "set_tick_speed", {"speed": str}, {"speed": {"SLOW", "NORMAL", "FAST"}}),
    }

    def __init__(self, trading_system=None):
        self.system = trading_system
        self.last_command_result = {"status": "IDLE", "action": None, "error": None}

    def attach_runtime(self, trading_system) -> None:
        self.system = trading_system

    @staticmethod
    def _build_pnl_coord(tick: Any, account: Any) -> Dict[str, float]:
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
        broker_control = (
            self.system.broker.control_snapshot()
            if hasattr(self.system.broker, "control_snapshot")
            else {}
        )
        vssf_control = (
            self.system.vssf.control_snapshot()
            if hasattr(self.system.vssf, "control_snapshot")
            else {}
        )
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
                "control": broker_control,
                "vssf_control": vssf_control,
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
            "command": dict(self.last_command_result),
        }

    @staticmethod
    def _build_payoff(positions: Dict[str, Any], current_price: float):
        points = []
        for i in range(-20, 21):
            x = current_price + i
            pnl = 0.0
            for value in positions.values():
                if not isinstance(value, dict):
                    continue
                qty = float(value.get("qty", 0))
                entry = float(value.get("avg_price", value.get("price", current_price)))
                sign = 1.0 if str(value.get("side", "BUY")).upper() == "BUY" else -1.0
                pnl += (x - entry) * qty * sign
            points.append({"x": x, "y": pnl})
        return points

    @classmethod
    def _validate_command(cls, command: Dict[str, Any]) -> str:
        if not isinstance(command, dict):
            raise UICommandError("command must be an object")
        action = command.get("action")
        if action not in cls._COMMAND_SPECS:
            raise UICommandError(f"unknown action: {action}")
        _, _, required, choices = cls._COMMAND_SPECS[action]
        for name, expected in required.items():
            if name not in command:
                raise UICommandError(f"missing payload: {name}")
            value = command[name]
            if isinstance(expected, tuple):
                if isinstance(value, bool) or not isinstance(value, expected):
                    raise UICommandError(f"invalid type: {name}")
            elif not isinstance(value, expected):
                raise UICommandError(f"invalid type: {name}")
        for name, allowed in choices.items():
            if command[name] not in allowed:
                raise UICommandError(f"invalid value: {name}")
        return action

    async def handle_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        action = command.get("action") if isinstance(command, dict) else None
        try:
            action = self._validate_command(command)
            if self.system is None:
                raise UICommandError("runtime unavailable: trading_system")
            target_name, method_name, required, _ = self._COMMAND_SPECS[action]
            target = getattr(self.system, target_name, None)
            method = getattr(target, method_name, None) if target is not None else None
            if not callable(method):
                raise UICommandError(f"runtime control method not implemented: {target_name}.{method_name}")
            payload = {name: command[name] for name in required}
            result = method(**payload)
            if inspect.isawaitable(result):
                await result
            self.last_command_result = {"status": "APPLIED", "action": action, "error": None}
        except Exception as exc:
            self.last_command_result = {"status": "REJECTED", "action": action, "error": str(exc)}
            logger.warning("UI command rejected: %s", exc)
        return dict(self.last_command_result)


class UIWebSocketHub:
    """실제 TradingSystem 상태를 하나의 WebSocket 경로로 fan-out."""

    def __init__(
        self,
        adapter: TargetArchitectureUIServer,
        host: str = "127.0.0.1",
        port: int = 8765,
        throttle_interval: float = 0.05,
    ):
        self.adapter = adapter
        self.host = host
        self.port = port
        self.throttle_interval = throttle_interval
        self.last_broadcast_time: float = 0.0
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
        now = time.monotonic()
        if now - self.last_broadcast_time < self.throttle_interval:
            return
        self.last_broadcast_time = now
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
