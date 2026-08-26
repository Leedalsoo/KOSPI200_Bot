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

def build_instrument_key(
    symbol: str = "KOSPI200",
    asset_type: Any = "OPTION",
    strike: float = 0.0,
    option_type: Any = None,
    expiry: str = "",
) -> str:
    """정규화된 Instrument Identity Key 생성.
    
    포맷:
    - FUTURES: {symbol}_FUTURES_{expiry} 또는 {symbol}_FUTURES
    - OPTION: {symbol}_OPTION_{expiry}_{option_type}_{strike:.1f} 또는 {symbol}_OPTION_{option_type}_{strike:.1f}
    - 레거시 기본 OPTION (옵션 세부속성 미지정): {symbol}_OPTION
    """
    sym = str(symbol or "KOSPI200").strip()
    a_type = asset_type.value if hasattr(asset_type, "value") else str(asset_type or "OPTION")
    exp = str(expiry or "").strip()
    if a_type == "FUTURES":
        return f"{sym}_FUTURES_{exp}" if exp else f"{sym}_FUTURES"

    # 옵션 세부정보가 없는 레거시 기본 옵션 호환
    if option_type is None and strike == 0.0 and not exp:
        return f"{sym}_OPTION"

    opt_type = option_type.value if hasattr(option_type, "value") else (str(option_type) if option_type else "CALL")
    stk_str = f"{float(strike):.1f}" if strike else "0.0"
    if exp:
        return f"{sym}_OPTION_{exp}_{opt_type}_{stk_str}"
    return f"{sym}_OPTION_{opt_type}_{stk_str}"



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
    symbol: str = "KOSPI200"
    expiry: str = ""
    tag_id: str = ""

    def get_instrument_key(self) -> str:
        return build_instrument_key(
            symbol=self.symbol,
            asset_type=self.asset_type,
            strike=self.strike,
            option_type=self.option_type,
            expiry=self.expiry,
        )


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
    symbol: str = "KOSPI200"
    option_type: Optional[CanonicalOptionType] = None
    strike: float = 0.0
    expiry: str = ""

    def get_instrument_key(self) -> str:
        return build_instrument_key(
            symbol=self.symbol,
            asset_type=self.asset_type,
            strike=self.strike,
            option_type=self.option_type,
            expiry=self.expiry,
        )


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

@dataclass(frozen=True)
class CanonicalStrategySignal:
    """[Strategy ➔ Signal Generator 전략 신호 DTO]"""
    signal_id: str
    track_id: str
    asset_type: CanonicalAssetType
    side: CanonicalOrderSide
    qty: int
    price: float
    option_type: Optional[CanonicalOptionType] = None
    strike: float = 0.0
    tag_id: str = ""
    reason: str = ""
    timestamp: str = ""
