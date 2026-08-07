# -*- coding: utf-8 -*-
from decimal import Decimal
from datetime import datetime
from uuid import uuid4

from core.contracts import ExecutionReport, OrderStatus, OrderPurpose
from position.position_manager import PositionManager

def test_position_manager_entry_and_wap() -> None:
    pm = PositionManager()
    
    # 1. 1차 진입 (Track 1, BUY 1계약 @ 2.00)
    rep1 = ExecutionReport(
        client_order_id=uuid4(),
        broker_order_id="ORD1",
        fill_id="FILL1",
        status=OrderStatus.FILLED,
        filled_qty=1,
        filled_price=Decimal("2.00"),
        remaining_qty=0,
        timestamp=datetime.now(),
        raw_response={},
        execution_price=Decimal("2.00"),
        strategy_id="Track1",
        order_purpose=OrderPurpose.STRATEGY_ENTRY
    )
    pos1 = pm.apply_execution(rep1)
    assert pos1.remaining_qty == 1
    assert pos1.entry_price == Decimal("2.00")
    assert pm.get_net_qty("Track1") == 1

    # 2. 2차 진입 (Track 1, BUY 1계약 추가 @ 3.00 -> 평단가 WAP = 2.50)
    rep2 = ExecutionReport(
        client_order_id=uuid4(),
        broker_order_id="ORD2",
        fill_id="FILL2",
        status=OrderStatus.FILLED,
        filled_qty=1,
        filled_price=Decimal("3.00"),
        remaining_qty=0,
        timestamp=datetime.now(),
        raw_response={},
        execution_price=Decimal("3.00"),
        strategy_id="Track1",
        order_purpose=OrderPurpose.STRATEGY_ENTRY
    )
    pos2 = pm.apply_execution(rep2)
    assert pos2.remaining_qty == 2
    assert pos2.entry_price == Decimal("2.50")
    assert pm.get_net_qty("Track1") == 2
    assert pm.get_gross_qty() == 2

    # 3. 3차 청산 (Track 1, EXIT 1계약 -> remaining = 1)
    rep3 = ExecutionReport(
        client_order_id=uuid4(),
        broker_order_id="ORD3",
        fill_id="FILL3",
        status=OrderStatus.FILLED,
        filled_qty=1,
        filled_price=Decimal("2.80"),
        remaining_qty=0,
        timestamp=datetime.now(),
        raw_response={},
        execution_price=Decimal("2.80"),
        strategy_id="Track1",
        order_purpose=OrderPurpose.STRATEGY_EXIT
    )
    pos3 = pm.apply_execution(rep3)
    assert pos3.remaining_qty == 1
    assert pos3.status == "PARTIALLY_CLOSED"
    assert pm.get_net_qty("Track1") == 1
