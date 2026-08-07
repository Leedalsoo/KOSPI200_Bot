# -*- coding: utf-8 -*-
from dataclasses import dataclass, asdict
from decimal import Decimal
from typing import Dict, Any, List
from datetime import datetime

from core.contracts import AccountSnapshot, PnLSnapshot

@dataclass(slots=True, frozen=True)
class TelemetryDTO:
    """[Phase 13 Frontend Telemetry DTO]
    
    Frontend UI(HFT Control Panel)로 브로드캐스트되는 표준화된 관측성 데이터 구조.
    """
    timestamp: str
    system_status: str
    realized_pnl: float
    unrealized_pnl: float
    strategy_pnl: float
    hedge_pnl: float
    fee: float
    slippage: float
    net_pnl: float
    cash_balance: float
    total_equity: float
    used_margin: float
    available_margin: float
    gross_position_qty: int
    net_position_qty: int

    @classmethod
    def from_snapshots(
        cls,
        account: AccountSnapshot,
        pnl: PnLSnapshot,
        gross_qty: int,
        net_qty: int,
        system_status: str = "NORMAL"
    ) -> "TelemetryDTO":
        return cls(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            system_status=system_status,
            realized_pnl=float(pnl.realized_pnl),
            unrealized_pnl=float(pnl.unrealized_pnl),
            strategy_pnl=float(pnl.strategy_pnl),
            hedge_pnl=float(pnl.hedge_pnl),
            fee=float(pnl.fee),
            slippage=float(pnl.slippage),
            net_pnl=float(pnl.net_pnl),
            cash_balance=float(account.cash),
            total_equity=float(account.total_equity),
            used_margin=float(account.used_margin),
            available_margin=float(account.available_margin),
            gross_position_qty=gross_qty,
            net_position_qty=net_qty
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
