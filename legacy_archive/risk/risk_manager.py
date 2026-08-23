# -*- coding: utf-8 -*-
from decimal import Decimal, ROUND_DOWN
import logging
import time
import hashlib
from typing import Optional

from core.contracts import OrderRequest, OrderStatus, RiskApprovalToken
from core.bus import EventBus, EventPriority
from fsm.oms_fsm import OmsFsm

logger = logging.getLogger(__name__)

class RiskManager:
    """Pre-Trade 리스크 수문장 (Fat-Finger 및 수량 제한 검증, VPIN/Margin 통합)"""
    
    def __init__(self, bus: EventBus, fsm: OmsFsm, max_qty: int, max_deviation_pct: Decimal) -> None:
        self.bus = bus
        self.fsm = fsm
        self.max_qty = max_qty
        self.max_deviation_pct = max_deviation_pct

    def _quantize_down(self, value: Decimal, precision: str = "0.00") -> Decimal:
        """[목표 C] 증권사 틱 규격 불일치를 막기 위한 ROUND_DOWN 강제 유틸리티"""
        return value.quantize(Decimal(precision), rounding=ROUND_DOWN)

    async def validate_order(self, request: OrderRequest, best_market_price: Decimal, current_vpin: Decimal = Decimal("0.0"), current_position: int = 0, margin_available: Decimal = Decimal("999999999.0")) -> Optional[RiskApprovalToken]:
        """[목표 A, B] 한도 초과 차단, VPIN/증거금 체크. 실패 시 FSM REJECTED 전이 및 Bus 전파"""
        
        # 1. Latency Check
        entry_time = time.time_ns()
        # 주문 생성 시각과 진입 시각의 차 (1ms = 1_000_000 ns)
        if request.timestamp_ns > 0 and (entry_time - request.timestamp_ns) > 10_000_000:
            await self.fsm.transition(request.client_order_id, OrderStatus.REJECTED)
            await self.bus.publish(EventPriority.RISK, "RISK_REJECT", {"reason": "latency_exceeded", "order_id": request.client_order_id})
            return None
        
        # 2. VPIN Filter (독성 회피)
        if current_vpin > Decimal("0.8"):
            await self.fsm.transition(request.client_order_id, OrderStatus.REJECTED)
            await self.bus.publish(EventPriority.RISK, "RISK_REJECT", {"reason": "vpin_exceeded", "order_id": request.client_order_id})
            return None

        # 3. Position / Margin Check
        if current_position + request.qty > self.max_qty:
            await self.fsm.transition(request.client_order_id, OrderStatus.REJECTED)
            await self.bus.publish(EventPriority.RISK, "RISK_REJECT", {
                "reason": "max_qty_exceeded",
                "order_id": request.client_order_id,
                "qty": request.qty,
                "max_qty": self.max_qty
            })
            return None
            
        estimated_cost = self._quantize_down(request.price * Decimal(request.qty))
        if estimated_cost > margin_available:
            await self.fsm.transition(request.client_order_id, OrderStatus.REJECTED)
            await self.bus.publish(EventPriority.RISK, "RISK_REJECT", {"reason": "insufficient_margin", "order_id": request.client_order_id})
            return None

        # 4. 가격 한도 체크 (Fat-Finger)
        # float 오염 방지를 위해 Decimal 연산 강제
        max_deviation = best_market_price * self.max_deviation_pct
        upper_bound = best_market_price + max_deviation
        lower_bound = best_market_price - max_deviation
        
        if request.price > upper_bound or request.price < lower_bound:
            await self.fsm.transition(request.client_order_id, OrderStatus.REJECTED)
            await self.bus.publish(EventPriority.RISK, "RISK_REJECT", {
                "reason": "fat_finger_pricing",
                "order_id": request.client_order_id,
                "price": request.price,
                "best_market_price": best_market_price
            })
            return None
            
        # 5. RiskApprovalToken 발급
        signature = hashlib.sha256(request.client_order_id.bytes).hexdigest()
        return RiskApprovalToken(request.client_order_id, time.time_ns(), signature)
