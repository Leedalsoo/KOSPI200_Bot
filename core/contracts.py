# -*- coding: utf-8 -*-
import struct
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime
from uuid import UUID
from enum import Enum
from typing import List, Dict, Any

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
    volume: int
    bid_prices: List[Decimal]
    ask_prices: List[Decimal]
    bid_qtys: List[int]
    ask_qtys: List[int]

@dataclass(slots=True, frozen=True)
class OrderRequest:
    decision_id: UUID
    client_order_id: UUID
    instrument_code: str
    price: Decimal
    qty: int
    side: str
    timestamp_ns: int = 0
    
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

