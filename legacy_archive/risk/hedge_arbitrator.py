# -*- coding: utf-8 -*-
from decimal import Decimal
from typing import List, Dict, Any, Optional, Tuple

from core.contracts import OrderRequest, OrderPurpose

class HedgeArbitrator:
    """[Phase 7 Virtual Broker Hedge Deduplication & Arbitration Engine]
    
    동일 틱/동일 시점에 복수의 전략(Track 1, 6, 7, 8, 9 등)에서 중복 발주되는
    헷지 Intent를 검증하여 과잉 헷지 및 중복 비용 발생을 차단하는 중재 엔진.
    """
    def __init__(self) -> None:
        self.recent_hedge_orders: Dict[str, OrderRequest] = {}

    def arbitrate_hedge_order(self, order: OrderRequest) -> Tuple[bool, str]:
        """헷지 주문의 중복 여부 및 중재(Arbitration) 실행
        
        Return: (is_approved, reason)
        """
        if order.order_purpose != OrderPurpose.RISK_HEDGE:
            return True, "NOT_HEDGE"

        hedge_key = f"{order.strategy_id}_{order.instrument_code}_{order.side}_{order.qty}"
        
        # 동일 전략, 동일 종목, 동일 수량의 헷지 주문 중복 방지
        if hedge_key in self.recent_hedge_orders:
            prev_order = self.recent_hedge_orders[hedge_key]
            # 최근 timestamp_ns 차이가 1초(1_000_000_000 ns) 이하인 경우 중복 차단
            if order.timestamp_ns > 0 and prev_order.timestamp_ns > 0:
                diff_ns = abs(order.timestamp_ns - prev_order.timestamp_ns)
                if diff_ns < 1_000_000_000:
                    return False, f"DUPLICATE_HEDGE_ORDER_BLOCKED (diff_ns: {diff_ns})"

        self.recent_hedge_orders[hedge_key] = order
        return True, "HEDGE_APPROVED"
