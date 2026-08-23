"""Canonical Contracts for Shared Boundaries."""
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from datetime import datetime

@dataclass
class CanonicalExecutionReport:
    execution_id: str
    order_id: str
    symbol: str
    side: str
    price: float
    quantity: int
    executed_at: datetime
    fee: float = 0.0
    slippage: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class CanonicalOrderCommand:
    order_id: str
    symbol: str
    side: str
    order_type: str
    price: float
    quantity: int
    created_at: datetime
    group_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class CanonicalPositionSnapshot:
    symbol: str
    quantity: int
    average_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float
    updated_at: datetime

@dataclass
class CanonicalAccountSummary:
    account_id: str
    total_balance: float
    used_margin: float
    free_margin: float
    realized_pnl: float
    unrealized_pnl: float
    updated_at: datetime
