# -*- coding: utf-8 -*-
from decimal import Decimal
from core.contracts import AccountSnapshot, PnLSnapshot
from infra.telemetry_dto import TelemetryDTO

def test_telemetry_dto_serialization() -> None:
    account = AccountSnapshot(
        initial_capital=Decimal("25000000.00"),
        cash=Decimal("25998000.00"),
        available_funds=Decimal("23998000.00"),
        used_margin=Decimal("2000000.00"),
        available_margin=Decimal("23998000.00"),
        total_equity=Decimal("26498000.00")
    )
    pnl = PnLSnapshot(
        realized_pnl=Decimal("1000000.00"),
        unrealized_pnl=Decimal("500000.00"),
        strategy_pnl=Decimal("1000000.00"),
        hedge_pnl=Decimal("0.00"),
        fee=Decimal("1500.00"),
        slippage=Decimal("500.00"),
        net_pnl=Decimal("1498000.00")
    )
    
    dto = TelemetryDTO.from_snapshots(account, pnl, gross_qty=3, net_qty=1)
    data = dto.to_dict()
    
    assert data["realized_pnl"] == 1000000.0
    assert data["net_pnl"] == 1498000.0
    assert data["gross_position_qty"] == 3
    assert data["net_position_qty"] == 1
    assert data["system_status"] == "NORMAL"
