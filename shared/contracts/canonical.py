"""Shared Contracts: Canonical Data Transfer Objects & Domain Events."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional
from decimal import Decimal

class CanonicalOrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class CanonicalAssetType(str, Enum):
    FUTURES = "FUTURES"
    OPTION = "OPTION"

class CanonicalOptionType(str, Enum):
    CALL = "CALL"
    PUT = "PUT"

@dataclass(frozen=True)
class CanonicalMarketTick:
    """[VMS ➔ VSSF / OptionProgram 마켓 틱 DTO]"""
    timestamp: str
    underlying_price: float
    strike_price: float = 0.0
    option_type: str = "CALL"
    bid_price: float = 0.0
    ask_price: float = 0.0
    last_price: float = 0.0
    volume: int = 0
    seq_id: int = 0

@dataclass(frozen=True)
class CanonicalOrderCommand:
    """[OptionProgram ➔ VSSF 주문 명령 DTO]"""
    client_order_id: str
    track_id: str
    asset_type: CanonicalAssetType
    side: CanonicalOrderSide
    qty: int
    price: float
    option_type: Optional[CanonicalOptionType] = None
    strike: float = 0.0
    tag_id: str = ""

@dataclass(frozen=True)
class CanonicalExecutionReport:
    """[VSSF ➔ OptionProgram 체결 증명 DTO]"""
    exec_id: str
    client_order_id: str
    track_id: str
    asset_type: CanonicalAssetType
    side: CanonicalOrderSide
    executed_qty: int
    executed_price: float
    fee: float
    slippage: float
    timestamp: str

@dataclass(frozen=True)
class CanonicalAccountSnapshot:
    """[VSSF 계좌 현황 스냅샷]"""
    account_id: str
    balance: float
    realized_pnl: float
    unrealized_pnl: float
    used_margin: float
    free_margin: float
    timestamp: str

@dataclass
class CanonicalAccountSummary:
    """[VSSF 계좌 요약 DTO — UI/외부 계층과 상태 격리용]"""
    account_id: str
    total_balance: float
    realized_pnl: float
    unrealized_pnl: float
    used_margin: float
    free_margin: float
    timestamp: str = "2026-08-23 09:00:00"
    positions: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    @property
    def balance(self) -> float:
        return self.total_balance

    @balance.setter
    def balance(self, val: float) -> None:
        self.total_balance = val
