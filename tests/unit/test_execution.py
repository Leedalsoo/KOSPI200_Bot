import pytest
import orjson
import asyncio
from unittest.mock import AsyncMock, MagicMock
from decimal import Decimal
from datetime import datetime
from uuid import uuid4

from core.contracts import OrderRequest, OrderStatus
from core.bus import EventPriority
from fsm.oms_fsm import OmsFsm
from exchange.execution import ExecutionAgent

@pytest.mark.asyncio
async def test_execute_order_infinite_loop_defense() -> None:
    """[목표 A 검증] 예외 발생 시 attempt가 정상 증가하여 최대 재시도 후 종료되는지 증명"""
    bus = MagicMock()
    fsm = AsyncMock()
    agent = ExecutionAgent(bus, fsm, max_retries=2)
    
    mock_send = AsyncMock(return_value=False) # 계속 실패 모킹
    req = OrderRequest(uuid4(), uuid4(), "CODE", Decimal("350.0"), 10, "BUY")
    
    await agent.execute_order(req, mock_send)
    assert mock_send.call_count == 2  # max_retries 만큼만 실행되고 루프 탈출

@pytest.mark.asyncio
async def test_handle_report_mandatory_publishing() -> None:
    """[목표 B 검증] orjson 파싱, FSM 즉각 갱신 및 EventBus 전파 증명"""
    bus = AsyncMock()
    fsm = OmsFsm()
    agent = ExecutionAgent(bus, fsm)
    
    client_oid = uuid4()
    fsm.states[client_oid] = OrderStatus.SENT # FSM 내부 상태 딕셔너리 직접 주입
    
    # orjson 덤프 바이너리 시뮬레이션
    report_dict = {
        "client_order_id": str(client_oid),
        "broker_order_id": "B1",
        "fill_id": "F1",
        "status": "FILLED",
        "filled_qty": 10,
        "filled_price": "350.50",
        "remaining_qty": 0,
        "timestamp": datetime.now().isoformat(),
        "raw_response": {}
    }
    raw_payload = orjson.dumps(report_dict)
    
    await agent.handle_execution_report(raw_payload)
    
    assert fsm.get_status(client_oid) == OrderStatus.FILLED
    bus.publish.assert_called_once()

@pytest.mark.asyncio
async def test_partial_fill_gc_timeout() -> None:
    """[목표 C 검증] 3초 방치 잔량(Partial Fill) 강제 취소 GC 로직 증명"""
    bus = AsyncMock()
    fsm = MagicMock()
    fsm.get_status.return_value = OrderStatus.PARTIAL
    agent = ExecutionAgent(bus, fsm)
    
    client_oid = uuid4()
    # 타임아웃을 짧게(0.1초) 주어 빠른 검증
    gc_task = asyncio.create_task(agent._garbage_collect_orphans(client_oid, timeout=0.1))
    await gc_task
    
    # timeout 이후 취소 로직(예: bus.publish로 취소 요청 전파 등)이 호출되었는지 증명
    bus.publish.assert_called_with(EventPriority.EXECUTION, "CANCEL_ORDER", client_oid)

def test_queue_position_tracking() -> None:
    """[목표 D 검증] 대기열 불리 판단 및 취소 시그널 정상 도출 증명"""
    bus = MagicMock()
    fsm = MagicMock()
    agent = ExecutionAgent(bus, fsm)
    
    # 내 주문 수량 10, 현재 호가창 잔량 5. 내 위치가 호가창 잔량보다 크면 불리(취소)
    pos = agent._track_queue_position(uuid4(), my_qty=10, current_book_qty=5)
    assert pos == -1 # 취소를 의미하는 값 반환 가정
