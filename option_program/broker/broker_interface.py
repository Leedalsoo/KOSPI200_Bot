"""Phase 5: Dual Broker Interface & Paper/Shadow Trading Control Layer."""
import logging
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from enum import Enum

from shared.contracts.canonical import (
    CanonicalOrderCommand,
    CanonicalExecutionReport,
    CanonicalAccountSummary,
)
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime

logger = logging.getLogger(__name__)


class BrokerMode(str, Enum):
    PAPER = "PAPER"
    SHADOW = "SHADOW"
    REAL = "REAL"


class IBrokerAdapter(ABC):
    """Authoritative broker contract shared by PAPER, SHADOW and REAL adapters."""

    @abstractmethod
    def send_order(self, command: CanonicalOrderCommand) -> Optional[CanonicalExecutionReport]:
        pass

    @abstractmethod
    def cancel_order(self, client_order_id: str) -> bool:
        pass

    @abstractmethod
    def get_account_summary(self) -> CanonicalAccountSummary:
        pass

    @abstractmethod
    def get_positions(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        pass

    def set_connection(self, connected: bool) -> None:
        self._connected = bool(connected)

    def set_latency(self, latency_ms: float) -> None:
        value = float(latency_ms)
        if value < 0.0 or value > 5000.0:
            raise ValueError("latency_ms must be between 0 and 5000")
        self._latency_ms = value

    def set_execution_behavior(self, mode: str) -> None:
        value = str(mode).upper()
        if value not in {"NORMAL", "DELAYED", "REJECT"}:
            raise ValueError(f"unsupported execution behavior: {mode}")
        self._execution_behavior = value

    def control_snapshot(self) -> Dict[str, Any]:
        """Return the broker control state exposed to the UI layer."""
        return {
            "connected": self.is_connected(),
            "latency_ms": float(getattr(self, "_latency_ms", 0.0)),
            "execution_behavior": getattr(self, "_execution_behavior", "NORMAL"),
        }


class _ControllableBrokerMixin:
    """Common deterministic control behavior for non-live broker adapters."""

    _ALLOWED_EXECUTION_BEHAVIORS = {"NORMAL", "DELAYED", "REJECT"}

    def _init_control_state(self) -> None:
        self._latency_ms = 0.0
        self._execution_behavior = "NORMAL"

    def set_connection(self, connected: bool) -> None:
        self._connected = bool(connected)
        logger.info("[%s] connection=%s", type(self).__name__, self._connected)

    def set_latency(self, latency_ms: float) -> None:
        value = float(latency_ms)
        if value < 0.0 or value > 5000.0:
            raise ValueError("latency_ms must be between 0 and 5000")
        self._latency_ms = value

    def set_execution_behavior(self, mode: str) -> None:
        value = str(mode).upper()
        if value not in self._ALLOWED_EXECUTION_BEHAVIORS:
            raise ValueError(f"unsupported execution behavior: {mode}")
        self._execution_behavior = value

    def _before_send_order(self) -> bool:
        if not self._connected:
            return False
        if self._execution_behavior == "REJECT":
            logger.info("[%s] execution behavior REJECT blocked order", type(self).__name__)
            return False
        if self._execution_behavior == "DELAYED" and self._latency_ms > 0:
            time.sleep(self._latency_ms / 1000.0)
        return True

    def control_snapshot(self) -> Dict[str, Any]:
        return {
            "connected": self.is_connected(),
            "latency_ms": self._latency_ms,
            "execution_behavior": self._execution_behavior,
        }


class PaperBrokerAdapter(_ControllableBrokerMixin, IBrokerAdapter):
    """Official Paper Trading adapter backed by the authoritative VSSF runtime."""

    def __init__(
        self,
        vssf_runtime: Optional[VirtualSecuritiesFirmRuntime] = None,
        initial_capital: float = 25000000.0,
    ):
        self.vssf = (
            vssf_runtime
            if vssf_runtime is not None
            else VirtualSecuritiesFirmRuntime(initial_capital=initial_capital)
        )
        self._connected = True
        self._init_control_state()

    def send_order(self, command: CanonicalOrderCommand) -> Optional[CanonicalExecutionReport]:
        if not self._before_send_order():
            logger.warning("[PaperBroker] Order blocked by broker control state.")
            return None
        return self.vssf.process_order(command)

    def cancel_order(self, client_order_id: str) -> bool:
        return self._connected and self.vssf.cancel_order(client_order_id)

    def get_account_summary(self) -> CanonicalAccountSummary:
        return self.vssf.account.get_canonical_summary()

    def get_positions(self) -> Dict[str, Any]:
        return self.vssf.account.positions

    def is_connected(self) -> bool:
        return self._connected


class ShadowBrokerAdapter(_ControllableBrokerMixin, IBrokerAdapter):
    """Shadow adapter: mirrors orders into VSSF and never sends them to a real broker."""

    def __init__(
        self,
        vssf_runtime: Optional[VirtualSecuritiesFirmRuntime] = None,
        initial_capital: float = 25000000.0,
    ):
        self.vssf = (
            vssf_runtime
            if vssf_runtime is not None
            else VirtualSecuritiesFirmRuntime(initial_capital=initial_capital)
        )
        self._connected = True
        self.shadow_executions: List[CanonicalExecutionReport] = []
        self._init_control_state()

    def send_order(self, command: CanonicalOrderCommand) -> Optional[CanonicalExecutionReport]:
        if not self._before_send_order():
            logger.warning("[ShadowBroker] Order blocked by broker control state.")
            return None
        report = self.vssf.process_order(command)
        if report is not None:
            self.shadow_executions.append(report)
            logger.info(
                "[Shadow Execution] Order: %s | Price: %s | Qty: %s",
                report.client_order_id,
                report.executed_price,
                report.executed_qty,
            )
        return report

    def cancel_order(self, client_order_id: str) -> bool:
        return self._connected and self.vssf.cancel_order(client_order_id)

    def get_account_summary(self) -> CanonicalAccountSummary:
        return self.vssf.account.get_canonical_summary()

    def get_positions(self) -> Dict[str, Any]:
        return self.vssf.account.positions

    def is_connected(self) -> bool:
        return self._connected


class RealBrokerAdapterStub(IBrokerAdapter):
    """Compatibility stub retained for legacy imports; it never sends real orders."""

    def __init__(self, broker_name: str = "KIWOOM_OPENAPI"):
        self.broker_name = broker_name
        self._connected = False
        self._latency_ms = 0.0
        self._execution_behavior = "NORMAL"

    def connect(self) -> bool:
        self._connected = True
        return True

    def send_order(self, command: CanonicalOrderCommand) -> Optional[CanonicalExecutionReport]:
        if not self._connected or self._execution_behavior == "REJECT":
            return None
        if self._execution_behavior == "DELAYED" and self._latency_ms > 0:
            time.sleep(self._latency_ms / 1000.0)
        return None

    def cancel_order(self, client_order_id: str) -> bool:
        return self._connected

    def get_account_summary(self) -> CanonicalAccountSummary:
        return CanonicalAccountSummary(
            account_id="REAL-ACC-001",
            total_balance=0.0,
            used_margin=0.0,
            free_margin=0.0,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            timestamp="2026-08-24 09:00:00",
        )

    def get_positions(self) -> Dict[str, Any]:
        return {}

    def is_connected(self) -> bool:
        return self._connected

    def set_connection(self, connected: bool) -> None:
        self._connected = bool(connected)

    def set_latency(self, latency_ms: float) -> None:
        value = float(latency_ms)
        if value < 0.0 or value > 5000.0:
            raise ValueError("latency_ms must be between 0 and 5000")
        self._latency_ms = value

    def set_execution_behavior(self, mode: str) -> None:
        value = str(mode).upper()
        if value not in {"NORMAL", "DELAYED", "REJECT"}:
            raise ValueError(f"unsupported execution behavior: {mode}")
        self._execution_behavior = value

    def control_snapshot(self) -> Dict[str, Any]:
        return {
            "connected": self._connected,
            "latency_ms": self._latency_ms,
            "execution_behavior": self._execution_behavior,
        }


class BrokerFactory:
    """Unified switching mechanism between PAPER, SHADOW and REAL broker modes."""

    @staticmethod
    def create_broker(
        mode: BrokerMode = BrokerMode.PAPER,
        vssf_runtime: Optional[VirtualSecuritiesFirmRuntime] = None,
        broker_config: Optional[Any] = None,
    ) -> IBrokerAdapter:
        if mode == BrokerMode.PAPER:
            return PaperBrokerAdapter(vssf_runtime=vssf_runtime)
        if mode == BrokerMode.SHADOW:
            return ShadowBrokerAdapter(vssf_runtime=vssf_runtime)
        if mode == BrokerMode.REAL:
            from option_program.broker.real_broker_adapter import RealBrokerAdapter
            return RealBrokerAdapter(config=broker_config)
        raise ValueError(f"Unknown BrokerMode: {mode}")
