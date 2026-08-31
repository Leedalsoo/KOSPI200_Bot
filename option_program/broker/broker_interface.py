"""Phase 5: Dual Broker Interface & Paper/Shadow Trading Control Layer."""
import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
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


@dataclass
class BrokerOrderResponse:
    """브로커 주문 접수(ACK/Order ID) 순수 응답 객체 — 실제 체결 보고서(CanonicalExecutionReport)와 엄격히 분리."""
    success: bool
    broker_order_id: Optional[str]
    client_order_id: str
    status: str = "ACCEPTED"
    message: str = "Order accepted by broker"


class IBrokerAdapter(ABC):
    """Authoritative broker contract shared by PAPER, SHADOW and REAL adapters."""

    @abstractmethod
    def connect(self) -> bool:
        """브로커 세션 연결/인증 및 주문 가능 상태 전환."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """브로커 세션 연결 해제."""
        pass

    @abstractmethod
    def send_order(self, command: CanonicalOrderCommand) -> BrokerOrderResponse:
        """주문 접수/제출 (체결 이벤트와 엄격히 분리되며, ACK/broker_order_id 또는 실패 상세 반환)."""
        pass

    def poll_execution_reports(self) -> List[CanonicalExecutionReport]:
        """체결 이벤트 수신/폴링 (주문 접수와 분리된 별도 체결 전달 경로)."""
        return []

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
    def get_open_orders(self) -> List[Dict[str, Any]]:
        """[D-12] 미체결 활성 주문 목록 조회 (Recovery 및 상태 대사용)."""
        pass

    @abstractmethod
    def get_order_status(self, order_identifier: str) -> Optional[Dict[str, Any]]:
        """[D-12] 특정 주문(client_order_id 또는 broker_order_id)의 최신 상태 조회 (Recovery용)."""
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
            "connected": self._connected,
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
        self._pending_orders: List[CanonicalOrderCommand] = []
        self._order_status_history: Dict[str, Dict[str, Any]] = {}
        self._init_control_state()

    def send_order(self, command: CanonicalOrderCommand) -> BrokerOrderResponse:
        """주문 접수 및 식별자 반환 (이 시점에는 VSSF 체결을 처리하지 않고 대기 큐에 보관)."""
        if not self._connected:
            return BrokerOrderResponse(
                success=False,
                broker_order_id=None,
                client_order_id=command.client_order_id,
                status="DISCONNECTED",
                message="[PaperBroker] Broker is disconnected",
            )

        if self._execution_behavior == "REJECT":
            logger.info("[PaperBroker] execution behavior REJECT blocked order")
            return BrokerOrderResponse(
                success=False,
                broker_order_id=None,
                client_order_id=command.client_order_id,
                status="SAFETY_BLOCKED",
                message="[PaperBroker] Order blocked by execution behavior REJECT",
            )

        if self._execution_behavior == "DELAYED" and self._latency_ms > 0:
            time.sleep(self._latency_ms / 1000.0)

        # Pre-trade Risk 검증: 마진 부족 주문은 거부
        margin_required = self.vssf._controlled_order_margin(command)
        if self.vssf.account.free_margin < margin_required:
            logger.warning(
                "[PaperBroker] Order %s rejected: insufficient free margin (req=%.2f > free=%.2f)",
                command.client_order_id,
                margin_required,
                self.vssf.account.free_margin,
            )
            return BrokerOrderResponse(
                success=False,
                broker_order_id=None,
                client_order_id=command.client_order_id,
                status="REJECTED",
                message=f"[PaperBroker] Insufficient free margin: req={margin_required} > free={self.vssf.account.free_margin}",
            )

        broker_order_id = f"BRK-PAPER-{uuid.uuid4().hex[:8]}"
        self._pending_orders.append(command)
        order_info = {
            "broker_order_id": broker_order_id,
            "client_order_id": command.client_order_id,
            "symbol": command.symbol,
            "side": command.side.value if hasattr(command.side, "value") else str(command.side),
            "order_qty": command.qty,
            "executed_qty": 0,
            "unexecuted_qty": command.qty,
            "order_price": command.price,
            "status": "OPEN",
        }
        self._order_status_history[command.client_order_id] = order_info
        self._order_status_history[broker_order_id] = order_info
        return BrokerOrderResponse(
            success=True,
            broker_order_id=broker_order_id,
            client_order_id=command.client_order_id,
            status="ACCEPTED",
            message="Order successfully accepted by Paper Broker",
        )

    def poll_execution_reports(self) -> List[CanonicalExecutionReport]:
        """별도 체결 전달 경로: 대기 큐의 주문을 VSSF 매칭 엔진으로 체결 처리 후 보고서 반환."""
        reports: List[CanonicalExecutionReport] = []
        if not self._connected:
            return reports

        while self._pending_orders:
            cmd = self._pending_orders.pop(0)
            rep = self.vssf.process_order(cmd)
            if rep is not None:
                reports.append(rep)
                # 이력 갱신
                if cmd.client_order_id in self._order_status_history:
                    self._order_status_history[cmd.client_order_id]["status"] = "FILLED"
                    self._order_status_history[cmd.client_order_id]["executed_qty"] = rep.executed_qty
                    self._order_status_history[cmd.client_order_id]["unexecuted_qty"] = 0
        return reports

    def cancel_order(self, client_order_id: str) -> bool:
        # 대기 중인 주문이 있다면 먼저 제거
        self._pending_orders = [cmd for cmd in self._pending_orders if cmd.client_order_id != client_order_id]
        if client_order_id in self._order_status_history:
            self._order_status_history[client_order_id]["status"] = "CANCELLED"
        return self._connected and self.vssf.cancel_order(client_order_id)

    def get_account_summary(self) -> CanonicalAccountSummary:
        return self.vssf.account.get_canonical_summary()

    def get_positions(self) -> Dict[str, Any]:
        return self.vssf.account.positions

    def get_open_orders(self) -> List[Dict[str, Any]]:
        """[D-12] 미체결 활성 주문 목록 조회"""
        open_orders: List[Dict[str, Any]] = []
        for cmd in self._pending_orders:
            open_orders.append({
                "broker_order_id": f"BRK-PAPER-{cmd.client_order_id}",
                "client_order_id": cmd.client_order_id,
                "symbol": cmd.symbol,
                "side": cmd.side.value if hasattr(cmd.side, "value") else str(cmd.side),
                "order_qty": cmd.qty,
                "executed_qty": 0,
                "unexecuted_qty": cmd.qty,
                "order_price": cmd.price,
                "status": "OPEN",
            })
        return open_orders

    def get_order_status(self, order_identifier: str) -> Optional[Dict[str, Any]]:
        """[D-12] 특정 주문 상태 조회"""
        for cmd in self._pending_orders:
            if cmd.client_order_id == order_identifier or f"BRK-PAPER-{cmd.client_order_id}" == order_identifier:
                return {
                    "broker_order_id": f"BRK-PAPER-{cmd.client_order_id}",
                    "client_order_id": cmd.client_order_id,
                    "symbol": cmd.symbol,
                    "side": cmd.side.value if hasattr(cmd.side, "value") else str(cmd.side),
                    "order_qty": cmd.qty,
                    "executed_qty": 0,
                    "unexecuted_qty": cmd.qty,
                    "order_price": cmd.price,
                    "status": "OPEN",
                }
        if order_identifier in self._order_status_history:
            return self._order_status_history[order_identifier]
        return None

    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False


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
        self._pending_orders: List[CanonicalOrderCommand] = []
        self.shadow_executions: List[CanonicalExecutionReport] = []
        self._init_control_state()

    def send_order(self, command: CanonicalOrderCommand) -> BrokerOrderResponse:
        if not self._connected:
            return BrokerOrderResponse(
                success=False,
                broker_order_id=None,
                client_order_id=command.client_order_id,
                status="DISCONNECTED",
                message="[ShadowBroker] Broker is disconnected",
            )

        if self._execution_behavior == "REJECT":
            logger.info("[ShadowBroker] execution behavior REJECT blocked order")
            return BrokerOrderResponse(
                success=False,
                broker_order_id=None,
                client_order_id=command.client_order_id,
                status="SAFETY_BLOCKED",
                message="[ShadowBroker] Order blocked by execution behavior REJECT",
            )

        if self._execution_behavior == "DELAYED" and self._latency_ms > 0:
            time.sleep(self._latency_ms / 1000.0)

        margin_required = self.vssf._controlled_order_margin(command)
        if self.vssf.account.free_margin < margin_required:
            logger.warning(
                "[ShadowBroker] Order %s rejected: insufficient free margin",
                command.client_order_id,
            )
            return BrokerOrderResponse(
                success=False,
                broker_order_id=None,
                client_order_id=command.client_order_id,
                status="REJECTED",
                message="[ShadowBroker] Insufficient free margin",
            )

        broker_order_id = f"BRK-SHADOW-{uuid.uuid4().hex[:8]}"
        self._pending_orders.append(command)
        return BrokerOrderResponse(
            success=True,
            broker_order_id=broker_order_id,
            client_order_id=command.client_order_id,
            status="ACCEPTED",
            message="Order successfully accepted by Shadow Broker",
        )

    def poll_execution_reports(self) -> List[CanonicalExecutionReport]:
        reports: List[CanonicalExecutionReport] = []
        if not self._connected:
            return reports

        while self._pending_orders:
            cmd = self._pending_orders.pop(0)
            rep = self.vssf.process_order(cmd)
            if rep is not None:
                self.shadow_executions.append(rep)
                reports.append(rep)
                logger.info(
                    "[Shadow Execution] Order: %s | Price: %s | Qty: %s",
                    rep.client_order_id,
                    rep.executed_price,
                    rep.executed_qty,
                )
        return reports

    def cancel_order(self, client_order_id: str) -> bool:
        self._pending_orders = [cmd for cmd in self._pending_orders if cmd.client_order_id != client_order_id]
        return self._connected and self.vssf.cancel_order(client_order_id)

    def get_account_summary(self) -> CanonicalAccountSummary:
        return self.vssf.account.get_canonical_summary()

    def get_positions(self) -> Dict[str, Any]:
        return self.vssf.account.positions

    def get_open_orders(self) -> List[Dict[str, Any]]:
        """[D-12] 미체결 활성 주문 목록 조회"""
        open_orders: List[Dict[str, Any]] = []
        for cmd in self._pending_orders:
            open_orders.append({
                "broker_order_id": f"BRK-SHADOW-{cmd.client_order_id}",
                "client_order_id": cmd.client_order_id,
                "symbol": cmd.symbol,
                "side": cmd.side.value if hasattr(cmd.side, "value") else str(cmd.side),
                "order_qty": cmd.qty,
                "executed_qty": 0,
                "unexecuted_qty": cmd.qty,
                "order_price": cmd.price,
                "status": "OPEN",
            })
        return open_orders

    def get_order_status(self, order_identifier: str) -> Optional[Dict[str, Any]]:
        """[D-12] 특정 주문 상태 조회"""
        for cmd in self._pending_orders:
            if cmd.client_order_id == order_identifier or f"BRK-SHADOW-{cmd.client_order_id}" == order_identifier:
                return {
                    "broker_order_id": f"BRK-SHADOW-{cmd.client_order_id}",
                    "client_order_id": cmd.client_order_id,
                    "symbol": cmd.symbol,
                    "side": cmd.side.value if hasattr(cmd.side, "value") else str(cmd.side),
                    "order_qty": cmd.qty,
                    "executed_qty": 0,
                    "unexecuted_qty": cmd.qty,
                    "order_price": cmd.price,
                    "status": "OPEN",
                }
        return None

    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False


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

    def disconnect(self) -> None:
        self._connected = False

    def send_order(self, command: CanonicalOrderCommand) -> BrokerOrderResponse:
        if not self._connected:
            return BrokerOrderResponse(
                success=False,
                broker_order_id=None,
                client_order_id=command.client_order_id,
                status="DISCONNECTED",
                message="[RealBrokerStub] Broker is disconnected",
            )
        if self._execution_behavior == "REJECT":
            return BrokerOrderResponse(
                success=False,
                broker_order_id=None,
                client_order_id=command.client_order_id,
                status="SAFETY_BLOCKED",
                message="[RealBrokerStub] Execution behavior REJECT",
            )
        if self._execution_behavior == "DELAYED" and self._latency_ms > 0:
            time.sleep(self._latency_ms / 1000.0)
        return BrokerOrderResponse(
            success=True,
            broker_order_id=f"BRK-REAL-STUB-{uuid.uuid4().hex[:8]}",
            client_order_id=command.client_order_id,
            status="ACCEPTED",
            message="Stub order accepted"
        )

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

    def get_open_orders(self) -> List[Dict[str, Any]]:
        return []

    def get_order_status(self, order_identifier: str) -> Optional[Dict[str, Any]]:
        return None

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
