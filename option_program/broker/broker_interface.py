"""Phase 5: Dual Broker Interface & Paper Trading Adapter Layer.

Provides:
- IBrokerAdapter: Standard authoritative broker contract for Paper Trading (VSSF) and Real Brokers.
- PaperBrokerAdapter: High-fidelity authoritative paper trading wrapper around VSSF.
- RealBrokerAdapterStub: Production broker adapter stub for future real broker plug-in.
- BrokerFactory: Unified switching mechanism between PAPER and REAL broker modes.
"""
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from enum import Enum

from shared.contracts.canonical import (
    CanonicalOrderCommand,
    CanonicalExecutionReport,
    CanonicalAccountSummary
)
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime

logger = logging.getLogger(__name__)

class BrokerMode(str, Enum):
    PAPER = "PAPER"
    REAL = "REAL"

class IBrokerAdapter(ABC):
    """[Phase 5 브로커 인터페이스 표준 계약]"""
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

class PaperBrokerAdapter(IBrokerAdapter):
    """[Phase 5 공식 Paper Trading 어댑터]
    
    VSSF(가상 증권사) 단일 권위 금융 엔진을 감싸 IBrokerAdapter 표준 계약을 100% 충족함.
    """
    def __init__(self, vssf_runtime: Optional[VirtualSecuritiesFirmRuntime] = None, initial_capital: float = 25000000.0):
        self.vssf = vssf_runtime if vssf_runtime is not None else VirtualSecuritiesFirmRuntime(initial_capital=initial_capital)
        self._connected = True

    def send_order(self, command: CanonicalOrderCommand) -> Optional[CanonicalExecutionReport]:
        if not self._connected:
            logger.warning("[PaperBroker] Cannot send order while disconnected.")
            return None
        return self.vssf.process_order(command)

    def cancel_order(self, client_order_id: str) -> bool:
        # VSSF 호가창 취소
        return self.vssf.orderbook.cancel_order(client_order_id)

    def get_account_summary(self) -> CanonicalAccountSummary:
        return self.vssf.account.get_canonical_summary()

    def get_positions(self) -> Dict[str, Any]:
        return self.vssf.account.positions

    def is_connected(self) -> bool:
        return self._connected

class RealBrokerAdapterStub(IBrokerAdapter):
    """[Phase 5 실전 증권사 어댑터 스텁]
    
    향후 키움/LS/한투 등 실전 브로커 API 연동을 위한 규격 호환 스텁.
    """
    def __init__(self, broker_name: str = "KIWOOM_OPENAPI"):
        self.broker_name = broker_name
        self._connected = False

    def connect(self) -> bool:
        self._connected = True
        return True

    def send_order(self, command: CanonicalOrderCommand) -> Optional[CanonicalExecutionReport]:
        if not self._connected:
            logger.warning(f"[{self.broker_name}] Disconnected. Cannot send real order.")
            return None
        # 실전 증권사 API 호출 규격 매핑
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
            timestamp="2026-08-24 09:00:00"
        )

    def get_positions(self) -> Dict[str, Any]:
        return {}

    def is_connected(self) -> bool:
        return self._connected

class BrokerFactory:
    """[Phase 5 브로커 팩토리] 단 1개의 설정 플래그로 Paper / Real 브로커 스위칭"""
    @staticmethod
    def create_broker(mode: BrokerMode = BrokerMode.PAPER, vssf_runtime: Optional[VirtualSecuritiesFirmRuntime] = None) -> IBrokerAdapter:
        if mode == BrokerMode.PAPER:
            return PaperBrokerAdapter(vssf_runtime=vssf_runtime)
        elif mode == BrokerMode.REAL:
            return RealBrokerAdapterStub()
        else:
            raise ValueError(f"Unknown BrokerMode: {mode}")
