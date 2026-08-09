# -*- coding: utf-8 -*-
from decimal import Decimal
from datetime import datetime
from uuid import uuid4

from core.contracts import OrderRequest, OrderPurpose, OrderStatus
from execution.execution_engine import ExecutionEngine

def test_execution_engine_matching_buy() -> None:
    engine = ExecutionEngine(fee_rate=Decimal("0.00003"), tick_size=Decimal("0.05"), multiplier=Decimal("250000"))
    order = OrderRequest(
        decision_id=uuid4(),
        client_order_id=uuid4(),
        instrument_code="KOSPI200_OPT",
        price=Decimal("2.00"),
        qty=2,
        side="BUY",
        strategy_id="Track1",
        order_purpose=OrderPurpose.STRATEGY_ENTRY
    )
    
    report = engine.match_order(order, bid_price=Decimal("1.95"), ask_price=Decimal("2.00"), slippage_ticks=1)
    
    assert report.status == OrderStatus.FILLED
    assert report.filled_qty == 2
    assert report.execution_price == Decimal("2.05")  # 2.00 + 1 tick (0.05)
    assert report.slippage_cost == Decimal("25000.00")  # (2.05 - 2.00) * 2 * 250000 = 0.05 * 500000 = 25000
    assert report.fee > Decimal("0")
    assert report.strategy_id == "Track1"
