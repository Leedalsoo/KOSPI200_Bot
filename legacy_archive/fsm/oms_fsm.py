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

    def is_idempotent(self, order_id: uuid.UUID) -> bool:
        """주문 ID가 이미 등록되어 처리 중이거나 완료되었는지 여부 확인 (멱등성 가드)"""
        status = self.states.get(order_id)
        return status in (OrderStatus.NEW, OrderStatus.VALIDATED, OrderStatus.SENT, OrderStatus.ACCEPTED, OrderStatus.PENDING, OrderStatus.PARTIAL, OrderStatus.FILLED, OrderStatus.REJECTED, OrderStatus.CANCELLED)

    def clear_completed_locks(self) -> None:
        """종료 상태(FILLED, REJECTED, CANCELLED)에 도달한 주문의 메모리 락 정리"""
        completed = [oid for oid, status in self.states.items() if status in (OrderStatus.FILLED, OrderStatus.REJECTED, OrderStatus.CANCELLED)]
        for oid in completed:
            self._locks.pop(oid, None)
