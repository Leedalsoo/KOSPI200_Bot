# -*- coding: utf-8 -*-
import struct
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime
from uuid import UUID
from enum import Enum
from typing import List, Dict, Any, Tuple, Optional

class OrderStatus(str, Enum):
    NEW = "NEW"
    VALIDATED = "VALIDATED"
    SENT = "SENT"
    ACCEPTED = "ACCEPTED"
    PENDING = "PENDING"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    STANDBY_OVERRIDE = "STANDBY_OVERRIDE"

def calculate_weighted_average_price(
    current_qty: int,
    current_avg_price: Decimal,
    new_qty: int,
    new_fill_price: Decimal
) -> Decimal:
    """[P0 Pure Calculation Helper] 이동평균 평단가(Weighted Average Price) 산출 순수 함수.

    외부 상태를 직접 변경하지 않고 pure calculation 결과만 반환함.
    """
    safe_cur_qty = max(0, int(current_qty or 0))
    safe_new_qty = max(0, int(new_qty or 0))
    total_qty = safe_cur_qty + safe_new_qty

    if total_qty == 0:
        return Decimal("0.00")

    cur_p = Decimal(str(current_avg_price or "0.00"))
    new_p = Decimal(str(new_fill_price or "0.00"))
    total_cost = (Decimal(str(safe_cur_qty)) * cur_p) + (Decimal(str(safe_new_qty)) * new_p)
    return (total_cost / Decimal(str(total_qty))).quantize(Decimal("0.01"))

def calculate_available_funds(
    cash_balance: Decimal | float,
    pending_order_amount: Decimal | float,
    used_margin: Decimal | float
) -> Decimal:
    """[Account Helper] 가용 자금(Available Funds = Cash - Pending - Margin) 산출 순수 함수."""
    safe_cash = Decimal(str(cash_balance or "0.00"))
    safe_pending = Decimal(str(pending_order_amount or "0.00"))
    safe_margin = Decimal(str(used_margin or "0.00"))
    return max(Decimal("0.00"), safe_cash - safe_pending - safe_margin)

def calculate_available_margin(
    cash_balance: Decimal | float,
    used_margin: Decimal | float
) -> Decimal:
    """[Account Helper] 가용 증거금(Available Margin = Cash - Used Margin) 산출 순수 함수."""
    safe_cash = Decimal(str(cash_balance or "0.00"))
    safe_margin = Decimal(str(used_margin or "0.00"))
    return max(Decimal("0.00"), safe_cash - safe_margin)

def verify_account_integrity(
    cash_balance: Decimal | float,
    initial_capital: Decimal | float,
    realized_pnl: Decimal | float,
    total_fees: Decimal | float,
    total_slippage: Decimal | float
) -> Tuple[bool, str]:
    """[Account Integrity Guard] 계좌 잔고 정합성 등식 검증 유틸리티."""
    expected = Decimal(str(initial_capital or "0.00")) + Decimal(str(realized_pnl or "0.00")) - Decimal(str(total_fees or "0.00")) - Decimal(str(total_slippage or "0.00"))
    actual = Decimal(str(cash_balance or "0.00"))
    diff = abs(actual - expected)
    if diff > Decimal("0.05"):
        diag = f"[ACCOUNT_INTEGRITY_MISMATCH] Expected: {expected:.2f}, Actual: {actual:.2f}, Diff: {diff:.2f}"
        return False, diag
    return True, "OK"

class OrderPurpose(str, Enum):
    STRATEGY_ENTRY = "STRATEGY_ENTRY"
    STRATEGY_EXIT = "STRATEGY_EXIT"
    RISK_HEDGE = "RISK_HEDGE"
    REBALANCE = "REBALANCE"

@dataclass(slots=True, frozen=True)
class RiskApprovalToken:
    order_id: UUID
    timestamp_ns: int
    signature: str


@dataclass(slots=True, frozen=True)
class MarketTick:
    instrument_code: str
    timestamp: datetime
    last_price: Decimal
    volume: Optional[int] = None
    bid_prices: List[Decimal] = None
    ask_prices: List[Decimal] = None
    bid_qtys: List[int] = None
    ask_qtys: List[int] = None
    seq: int = 0
    bid_price: Optional[Decimal] = None
    ask_price: Optional[Decimal] = None
    bid_ask_spread: Decimal = Decimal("0")
    open_interest: Optional[int] = None
    scenario_id: Optional[str] = None

def validate_market_tick(
    current_tick: MarketTick,
    prev_tick: Optional[MarketTick] = None
) -> Tuple[bool, List[str]]:
    """[MarketTick Integrity Guard] 틱 무결성(seq, timestamp, price, bid/ask) 검증 순수 유틸리티."""
    errors: List[str] = []
    if current_tick.last_price <= Decimal("0"):
        errors.append("INVALID_PRICE")

    if current_tick.bid_price is not None and current_tick.ask_price is not None:
        if current_tick.bid_price > current_tick.ask_price:
            errors.append("INVALID_BID_ASK")

    if prev_tick is not None:
        if current_tick.seq <= prev_tick.seq and current_tick.seq != 0:
            if current_tick.seq == prev_tick.seq:
                errors.append("DUPLICATE_TICK")
            else:
                errors.append("TICK_SEQUENCE_ERROR")
        if current_tick.timestamp < prev_tick.timestamp:
            errors.append("TICK_TIMESTAMP_ERROR")

    return (len(errors) == 0), errors

@dataclass(slots=True, frozen=True)
class OrderRequest:
    decision_id: UUID
    client_order_id: UUID
    instrument_code: str
    price: Decimal
    qty: int
    side: str
    timestamp_ns: int = 0
    strategy_id: str = ""
    order_purpose: OrderPurpose = OrderPurpose.STRATEGY_ENTRY
    order_type: str = "LIMIT"
    parent_order_id: Any = None
    parent_position_id: Any = None
    hedge_ref_id: Any = None
    
    def to_struct(self) -> bytes:
        """[목표 C] 향후 mmap Zero-Copy를 위한 struct 바이너리 패킹 뼈대"""
        # decision_id (16 bytes), client_order_id (16 bytes)
        # instrument_code (12 bytes string padded)
        # price (double - 8 bytes)
        # qty (int32 - 4 bytes)
        # side (1 byte char: B or S)
        # format: 16s 16s 12s d i c
        side_char = b'B' if self.side == "BUY" else b'S'
        code_bytes = self.instrument_code.encode('ascii')[:12].ljust(12, b'\x00')
        return struct.pack(
            '<16s16s12sdic',
            self.decision_id.bytes,
            self.client_order_id.bytes,
            code_bytes,
            float(self.price),
            self.qty,
            side_char
        )

@dataclass(slots=True, frozen=True)
class ExecutionReport:
    client_order_id: UUID
    broker_order_id: str
    fill_id: str
    status: OrderStatus
    filled_qty: int
    filled_price: Decimal
    remaining_qty: int
    timestamp: datetime
    raw_response: Dict[str, Any]
    requested_price: Decimal = Decimal("0")
    market_price: Decimal = Decimal("0")
    execution_price: Decimal = Decimal("0")
    slippage_ticks: Decimal = Decimal("0")
    slippage_cost: Decimal = Decimal("0")
    fee: Decimal = Decimal("0")
    strategy_id: str = ""
    order_purpose: OrderPurpose = OrderPurpose.STRATEGY_ENTRY

class LimitOrderType(str, Enum):
    TP = "TP"
    TIME_EXIT = "TIME_EXIT"
    EMERGENCY = "EMERGENCY"
    SL = "SL"
    CANCEL = "CANCEL"

class PositionExitStatus(str, Enum):
    OPEN = "OPEN"
    PENDING_EXIT = "PENDING_EXIT"
    CLOSED = "CLOSED"
    PARTIALLY_CLOSED = "PARTIALLY_CLOSED"

@dataclass
class LimitOrderRecord:
    order_id: str
    position_id: str
    strategy_id: str
    side: str
    price: Decimal
    qty: int
    order_type: str
    status: str
    created_at_ns: int
    reprice_count: int = 0
    last_reprice_at_ns: int = 0

@dataclass
class PositionRecord:
    position_id: str
    strategy_id: str
    symbol: str
    side: str
    qty: int
    remaining_qty: int
    entry_price: Decimal
    option_type: str = "OPTIONS"
    strike_price: Decimal = Decimal("0")
    expiry: str = ""
    status: str = "OPEN"
    tag: str = ""
    entry_time: datetime = datetime.now()

