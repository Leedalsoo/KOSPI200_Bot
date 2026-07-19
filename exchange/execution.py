# -*- coding: utf-8 -*-
import asyncio
import orjson
import logging
from typing import Callable, Awaitable, Any, Dict
from uuid import UUID

from core.contracts import OrderRequest, OrderStatus
from core.bus import EventBus, EventPriority
from fsm.oms_fsm import OmsFsm

logger = logging.getLogger(__name__)

class ExecutionAgent:
    """주문 집행, 체결 수신 및 고아 주문 GC 관리 에이전트"""
    
    def __init__(self, bus: EventBus, fsm: OmsFsm, max_retries: int = 3) -> None:
        self.bus: EventBus = bus
        self.fsm: OmsFsm = fsm
        self.max_retries: int = max_retries
        self._partial_fills_monitor: Dict[UUID, asyncio.Task[Any]] = {}

    async def execute_order(self, request: OrderRequest, adapter_send_func: Callable[[OrderRequest], Awaitable[bool]]) -> None:
        """[목표 A] 지수 백오프 기반 전송 및 무한 루프 방어"""
        attempt = 0
        while attempt < self.max_retries:
            try:
                success = await adapter_send_func(request)
                if success:
                    # Successful send
                    return
                # If False, we retry
            except Exception as e:
                logger.error(f"Failed to send order {request.client_order_id}: {e}")
                
            attempt += 1
            if attempt < self.max_retries:
                await asyncio.sleep(0.1 * (2 ** attempt)) # Exponential backoff

    async def handle_execution_report(self, raw_payload: bytes) -> None:
        """[목표 B, C] orjson 파싱, FSM 전이, 버스 전파 및 Partial Fill GC 등록"""
        try:
            report_dict = orjson.loads(raw_payload)
        except orjson.JSONDecodeError as e:
            logger.error(f"Failed to decode execution report: {e}")
            return
            
        client_oid_str = report_dict.get("client_order_id")
        if not client_oid_str:
            return
            
        try:
            client_oid = UUID(client_oid_str)
        except ValueError:
            return
            
        status_str = report_dict.get("status", "")
        try:
            new_status = OrderStatus(status_str)
        except ValueError:
            return

        # FSM Transition
        await self.fsm.transition(client_oid, new_status)
        
        # EventBus Publish
        await self.bus.publish(EventPriority.EXECUTION, "EXECUTION_REPORT", report_dict)
        
        # Handle Partial Fill GC
        if new_status == OrderStatus.PARTIAL:
            if client_oid not in self._partial_fills_monitor:
                gc_task = asyncio.create_task(self._garbage_collect_orphans(client_oid))
                self._partial_fills_monitor[client_oid] = gc_task
        elif new_status in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED):
            # Clean up the task if it exists
            task = self._partial_fills_monitor.pop(client_oid, None)
            if task and not task.done():
                task.cancel()

    async def _garbage_collect_orphans(self, order_id: UUID, timeout: float = 3.0) -> None:
        """[목표 C] 3초 방치된 Partial Fill 주문 강제 취소 백그라운드 태스크"""
        try:
            await asyncio.sleep(timeout)
            
            # If we wake up and we are still running, it means we haven't been cancelled by a FILLED/CANCELLED event
            # Ensure the state is still PARTIAL before sending CANCEL
            current_status = self.fsm.get_status(order_id)
            if current_status == OrderStatus.PARTIAL:
                await self.bus.publish(EventPriority.EXECUTION, "CANCEL_ORDER", order_id)
                
        except asyncio.CancelledError:
            # We were cancelled because the order filled or cancelled normally
            pass
        finally:
            self._partial_fills_monitor.pop(order_id, None)

    def _track_queue_position(self, order_id: UUID, my_qty: int, current_book_qty: int) -> int:
        """[목표 D] 스마트 지정가 라우팅을 위한 대기열 위치 실시간 추적 및 불리 시 취소 판단"""
        # 내 주문 수량이 현재 호가창 잔량보다 많다는 것은, 허수 호가가 취소되었거나 내가 큐의 맨 뒤에 있어 체결 가능성이 낮다는 뜻
        if my_qty > current_book_qty:
            return -1 # 불리함(취소 시그널)
        return current_book_qty - my_qty # 대략적인 내 앞에 남은 잔량 반환
