# -*- coding: utf-8 -*-
from decimal import Decimal
from datetime import datetime
from uuid import uuid4

from core.contracts import ExecutionReport, OrderStatus, OrderPurpose
from pnl.pnl_engine import PnLEngine

def test_pnl_engine_7breakdown() -> None:
    pnl_engine = PnLEngine()
    
    # 1. Track 1 청산 체결 (Entry @ 2.00, Exit @ 3.00, Qty 1 -> Realized = +250,000 원)
    rep1 = ExecutionReport(
        client_order_id=uuid4(),
        broker_order_id="ORD1",
        fill_id="FILL1",
        status=OrderStatus.FILLED,
        filled_qty=1,
        filled_price=Decimal("3.00"),
        remaining_qty=0,
        timestamp=datetime.now(),
        raw_response={},
        execution_price=Decimal("3.00"),
        fee=Decimal("1500.00"),
        slippage_cost=Decimal("500.00"),
        strategy_id="Track1",
        order_purpose=OrderPurpose.STRATEGY_EXIT
    )
    pnl_engine.register_execution(rep1, entry_price=Decimal("2.00"))
    
    snap = pnl_engine.get_snapshot()
    assert snap.realized_pnl == Decimal("250000.00")
    assert snap.strategy_pnl == Decimal("250000.00")
    assert snap.fee == Decimal("1500.00")
    assert snap.slippage == Decimal("500.00")
    assert snap.net_pnl == Decimal("248000.00")  # 250,000 - 1500 - 500
