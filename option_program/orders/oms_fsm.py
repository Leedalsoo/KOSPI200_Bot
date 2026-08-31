# -*- coding: utf-8 -*-
"""OMS Finite State Machine (FSM) for Order Lifecycle Management.

Enforces valid forward order status transitions and strictly blocks:
- Terminal state re-transitions (FILLED, CANCELLED, REJECTED)
- Illegal backward transitions (e.g. SENT -> NEW, PARTIAL -> SENT, etc.)
- Transitions on uninitialized/invalid states
"""
import uuid
import asyncio
import logging
from typing import Dict, Optional, Set
from shared.core.contracts import OrderStatus, RiskApprovalToken

logger = logging.getLogger(__name__)

# 10개 OrderStatus의 합법적 허용 전이 규칙표 (순방향 전이, 취소 요청 분리 및 종료 상태 격리)
ALLOWED_TRANSITIONS: Dict[Optional[OrderStatus], Set[OrderStatus]] = {
    None: {
        OrderStatus.NEW,
        OrderStatus.VALIDATED,
        OrderStatus.SENT,
        OrderStatus.REJECTED,
    },
    OrderStatus.NEW: {
        OrderStatus.VALIDATED,
        OrderStatus.SENT,
        OrderStatus.ACCEPTED,
        OrderStatus.PENDING,
        OrderStatus.PARTIAL,
        OrderStatus.FILLED,
        OrderStatus.REJECTED,
        OrderStatus.CANCEL_REQUESTED,
    },
    OrderStatus.VALIDATED: {
        OrderStatus.SENT,
        OrderStatus.ACCEPTED,
        OrderStatus.PENDING,
        OrderStatus.PARTIAL,
        OrderStatus.FILLED,
        OrderStatus.REJECTED,
        OrderStatus.CANCEL_REQUESTED,
    },
    OrderStatus.SENT: {
        OrderStatus.ACCEPTED,
        OrderStatus.PENDING,
        OrderStatus.PARTIAL,
        OrderStatus.FILLED,
        OrderStatus.REJECTED,
        OrderStatus.CANCEL_REQUESTED,
    },
    OrderStatus.ACCEPTED: {
        OrderStatus.PENDING,
        OrderStatus.PARTIAL,
        OrderStatus.FILLED,
        OrderStatus.REJECTED,
        OrderStatus.CANCEL_REQUESTED,
    },
    OrderStatus.PENDING: {
        OrderStatus.PARTIAL,
        OrderStatus.FILLED,
        OrderStatus.REJECTED,
        OrderStatus.CANCEL_REQUESTED,
    },
    OrderStatus.PARTIAL: {
        OrderStatus.PARTIAL,
        OrderStatus.FILLED,
        OrderStatus.REJECTED,
        OrderStatus.CANCEL_REQUESTED,
    },
    OrderStatus.CANCEL_REQUESTED: {
        OrderStatus.CANCELLED,
        OrderStatus.PARTIAL,
        OrderStatus.FILLED,
        OrderStatus.REJECTED,
    },
    OrderStatus.FILLED: set(),      # 종료 상태 (전이 불가)
    OrderStatus.CANCELLED: set(),   # 종료 상태 (전이 불가)
    OrderStatus.REJECTED: set(),    # 종료 상태 (전이 불가)
}


class OmsFsm:
    """[OMS FSM] 주문 상태 전이 검증 및 수명주기 관리 머신"""

    def __init__(self) -> None:
        self.states: Dict[uuid.UUID, OrderStatus] = {}
        self._locks: Dict[uuid.UUID, asyncio.Lock] = {}

    def _get_lock(self, order_id: uuid.UUID) -> asyncio.Lock:
        if order_id not in self._locks:
            self._locks[order_id] = asyncio.Lock()
        return self._locks[order_id]

    @staticmethod
    def can_transition(from_status: Optional[OrderStatus], to_status: OrderStatus) -> bool:
        """현재 상태에서 대상 상태로의 전이 허용 여부 판정"""
        allowed = ALLOWED_TRANSITIONS.get(from_status, set())
        return to_status in allowed

    def _apply_transition(self, order_id: uuid.UUID, status: OrderStatus) -> bool:
        """내부 상태 전이 적용 (허용되지 않은 불법 전이 차단)"""
        current_status = self.states.get(order_id)
        if not self.can_transition(current_status, status):
            logger.warning(
                f"[OmsFsm] Illegal transition rejected for {order_id}: "
                f"{current_status} -> {status}"
            )
            return False
        self.states[order_id] = status
        return True

    async def register_order(self, token: RiskApprovalToken) -> bool:
        """RiskApprovalToken 기반 주문 등록 (NEW 상태)"""
        order_id = token.order_id

        # 1차 확인 (락 없이)
        current_status = self.states.get(order_id)
        if current_status in (OrderStatus.SENT, OrderStatus.REJECTED, OrderStatus.FILLED):
            return False

        async with self._get_lock(order_id):
            # 2차 확인 (Double-checked Locking)
            current_status = self.states.get(order_id)
            if current_status in (OrderStatus.SENT, OrderStatus.REJECTED, OrderStatus.FILLED):
                return False

            return self._apply_transition(order_id, OrderStatus.NEW)

    async def transition(self, order_id: uuid.UUID, status: OrderStatus) -> bool:
        """비동기 락 기반 주문 상태 전이"""
        async with self._get_lock(order_id):
            return self._apply_transition(order_id, status)

    def transition_sync(self, order_id: uuid.UUID, status: OrderStatus) -> bool:
        """동기 컨텍스트 주문 상태 전이"""
        return self._apply_transition(order_id, status)

    def get_status(self, order_id: uuid.UUID) -> Optional[OrderStatus]:
        """주문의 현재 상태 조회"""
        return self.states.get(order_id)

    def is_idempotent(self, order_id: uuid.UUID) -> bool:
        """주문 ID가 이미 등록되어 처리 중이거나 완료되었는지 여부 확인 (멱등성 가드)"""
        status = self.states.get(order_id)
        return status in (
            OrderStatus.NEW,
            OrderStatus.VALIDATED,
            OrderStatus.SENT,
            OrderStatus.ACCEPTED,
            OrderStatus.PENDING,
            OrderStatus.PARTIAL,
            OrderStatus.FILLED,
            OrderStatus.REJECTED,
            OrderStatus.CANCELLED,
        )

    def clear_completed_locks(self) -> None:
        """종료 상태(FILLED, REJECTED, CANCELLED)에 도달한 주문의 메모리 락 정리"""
        completed = [
            oid
            for oid, status in self.states.items()
            if status in (OrderStatus.FILLED, OrderStatus.REJECTED, OrderStatus.CANCELLED)
        ]
        for oid in completed:
            self._locks.pop(oid, None)
