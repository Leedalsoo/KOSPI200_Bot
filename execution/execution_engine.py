# -*- coding: utf-8 -*-
from decimal import Decimal
from datetime import datetime
from uuid import uuid4
from typing import Dict, Any, Optional

from core.contracts import OrderRequest, ExecutionReport, OrderStatus, OrderPurpose

class ExecutionEngine:
    """[Phase 3 Virtual Broker Execution Engine]
    
    OrderRequest를 전달받아 슬리피지/수수료 및 Matching을 계산하여
    표준 ExecutionReport를 방출하는 체결 전담 엔진.
    """
    def __init__(self, fee_rate: Decimal = Decimal("0.00003"), tick_size: Decimal = Decimal("0.05"), multiplier: Decimal = Decimal("250000")) -> None:
        self.fee_rate = fee_rate
        self.tick_size = tick_size
        self.multiplier = multiplier

    def match_order(
        self,
        order: OrderRequest,
        bid_price: Decimal,
        ask_price: Decimal,
        slippage_ticks: int = 0,
        timestamp: Optional[datetime] = None
    ) -> ExecutionReport:
        fill_timestamp = timestamp or datetime.now()
        
        # 1. Matching & Slippage Price Calculation
        if order.side == "BUY":
            base_price = ask_price if ask_price > Decimal("0") else order.price
            execution_price = base_price + (Decimal(str(slippage_ticks)) * self.tick_size)
        else:
            base_price = bid_price if bid_price > Decimal("0") else order.price
            execution_price = max(self.tick_size, base_price - (Decimal(str(slippage_ticks)) * self.tick_size))

        slippage_cost = abs(execution_price - order.price) * Decimal(str(order.qty)) * self.multiplier
        
        # 2. Fee Calculation (KOSPI200 Futures/Options Standard Fee)
        transaction_amount = execution_price * Decimal(str(order.qty)) * self.multiplier
        fee = (transaction_amount * self.fee_rate).quantize(Decimal("0.01"))

        # 3. ExecutionReport Assembly
        fill_id = f"FILL_{uuid4().hex[:12].upper()}"
        broker_order_id = f"ORD_{uuid4().hex[:8].upper()}"

        return ExecutionReport(
            client_order_id=order.client_order_id,
            broker_order_id=broker_order_id,
            fill_id=fill_id,
            status=OrderStatus.FILLED,
            filled_qty=order.qty,
            filled_price=execution_price,
            remaining_qty=0,
            timestamp=fill_timestamp,
            raw_response={"slippage_ticks": slippage_ticks},
            requested_price=order.price,
            market_price=base_price,
            execution_price=execution_price,
            slippage_ticks=Decimal(str(slippage_ticks)),
            slippage_cost=slippage_cost,
            fee=fee,
            strategy_id=order.strategy_id,
            order_purpose=order.order_purpose
        )
