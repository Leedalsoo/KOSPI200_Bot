# -*- coding: utf-8 -*-
import uuid
import asyncio
from typing import Dict, Optional
from core.contracts import OrderStatus, RiskApprovalToken

class OmsFsm:
    def __init__(self) -> None:
        self.states: Dict[uuid.UUID, OrderStatus] = {}
        self._locks: Dict[uuid.UUID, asyncio.Lock] = {}
        
    def _get_lock(self, order_id: uuid.UUID) -> asyncio.Lock:
        if order_id not in self._locks:
            self._locks[order_id] = asyncio.Lock()
        return self._locks[order_id]

    async def register_order(self, token: RiskApprovalToken) -> None:
        order_id = token.order_id
        
        # 1차 확인 (락 없이)
        current_status = self.states.get(order_id)
        if current_status in (OrderStatus.SENT, OrderStatus.REJECTED, OrderStatus.FILLED):
            return

        async with self._get_lock(order_id):
            # 2차 확인 (Double-checked Locking)
            current_status = self.states.get(order_id)
            if current_status in (OrderStatus.SENT, OrderStatus.REJECTED, OrderStatus.FILLED):
                return
            
            self.states[order_id] = OrderStatus.NEW

    async def transition(self, order_id: uuid.UUID, status: OrderStatus) -> None:
        async with self._get_lock(order_id):
            self.states[order_id] = status
        
    def get_status(self, order_id: uuid.UUID) -> Optional[OrderStatus]:
        return self.states.get(order_id)
