# -*- coding: utf-8 -*-
from decimal import Decimal
from uuid import uuid4

from core.contracts import OrderRequest, OrderPurpose
from risk.hedge_arbitrator import HedgeArbitrator

def test_hedge_arbitrator_deduplication() -> None:
    arbitrator = HedgeArbitrator()
    
    order1 = OrderRequest(
        decision_id=uuid4(),
        client_order_id=uuid4(),
        instrument_code="KOSPI200_OPT",
        price=Decimal("2.00"),
        qty=1,
        side="SELL",
        timestamp_ns=1_000_000_000,
        strategy_id="Track1",
        order_purpose=OrderPurpose.RISK_HEDGE
    )
    
    # 1. 1차 헷지 주문 승인
    ok1, msg1 = arbitrator.arbitrate_hedge_order(order1)
    assert ok1 is True
    assert msg1 == "HEDGE_APPROVED"

    # 2. 50ms 후 동일 헷지 주문 재발주 -> 중복 차단 (DUPLICATE_HEDGE_ORDER_BLOCKED)
    order2 = OrderRequest(
        decision_id=uuid4(),
        client_order_id=uuid4(),
        instrument_code="KOSPI200_OPT",
        price=Decimal("2.00"),
        qty=1,
        side="SELL",
        timestamp_ns=1_050_000_000,
        strategy_id="Track1",
        order_purpose=OrderPurpose.RISK_HEDGE
    )
    ok2, msg2 = arbitrator.arbitrate_hedge_order(order2)
    assert ok2 is False
    assert "DUPLICATE_HEDGE_ORDER_BLOCKED" in msg2
