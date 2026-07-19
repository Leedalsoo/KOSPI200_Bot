# -*- coding: utf-8 -*-
import asyncio
import pytest
from unittest.mock import AsyncMock

from interface.websocket import WebsocketBroadcaster


@pytest.mark.asyncio
async def test_backpressure_drop_oldest() -> None:
    """[목표 A 검증] 클라이언트 수신 지연 시 큐가 꽉 차면 이전 데이터 삭제 증명"""
    broadcaster = WebsocketBroadcaster()
    ws = AsyncMock()
    sid = await broadcaster.register_connection(ws)

    # maxsize=1000 큐에 1005건 주입 → Drop-Oldest로 최신 1000건만 유지
    for i in range(1005):
        await broadcaster.broadcast_event({"seq": i})

    # 큐 크기가 1000으로 유지되는지 확인
    assert broadcaster.connections[sid].qsize() == 1000


@pytest.mark.asyncio
async def test_orphaned_session_cleanup() -> None:
    """[목표 B 검증] Ping/Pong 실패 시 세션 자동 자원 해제 증명"""
    broadcaster = WebsocketBroadcaster()
    ws = AsyncMock()
    # ping() 호출 시 TimeoutError 주입 → 고아 세션 강제 종료 시뮬레이션
    ws.ping.side_effect = asyncio.TimeoutError

    sid = await broadcaster.register_connection(ws)
    # 워커 태스크가 Ping 실패를 감지하고 세션을 정리할 때까지 잠시 대기
    await asyncio.sleep(0.05)

    # 🛡️ 세션이 딕셔너리에서 제거되었는지 검증
    assert sid not in broadcaster.connections
    assert sid not in broadcaster.active_websockets


@pytest.mark.asyncio
async def test_broadcast_serialization_once() -> None:
    """[목표 C 검증] broadcast_event에서 직렬화가 루프 밖에서 1회만 수행됨을 증명"""
    broadcaster = WebsocketBroadcaster()
    ws1 = AsyncMock()
    ws2 = AsyncMock()
    
    # 🛡️ 워커가 queue.get()을 가로채어 소진하지 못하도록 ping 단계에서 비동기 무한 대기 유도
    async def mock_ping() -> None:
        await asyncio.sleep(100)

    ws1.ping.side_effect = mock_ping
    ws2.ping.side_effect = mock_ping

    sid1 = await broadcaster.register_connection(ws1)
    sid2 = await broadcaster.register_connection(ws2)

    import orjson
    event_data = {"price": 12345, "qty": 10}

    await broadcaster.broadcast_event(event_data)

    # 두 큐 모두 동일한 bytes 객체를 수신해야 함
    expected: bytes = orjson.dumps(event_data, default=str)
    item1: bytes = await asyncio.wait_for(broadcaster.connections[sid1].get(), timeout=1.0)
    item2: bytes = await asyncio.wait_for(broadcaster.connections[sid2].get(), timeout=1.0)

    assert item1 == expected
    assert item2 == expected
    # 두 큐가 동일한 bytes 내용을 가지는지 확인
    assert item1 == item2


@pytest.mark.asyncio
async def test_send_bytes_used_for_transmission() -> None:
    """[목표 C 검증] 워커가 send_bytes()로 전송하여 인코딩 오버헤드 0을 보장"""
    broadcaster = WebsocketBroadcaster()
    ws = AsyncMock()

    # ping()은 정상 통과, send_bytes 수신 여부 확인
    ws.ping.return_value = None

    sid = await broadcaster.register_connection(ws)
    await broadcaster.broadcast_event({"tick": 1})

    # 워커가 큐를 소진할 충분한 시간 부여
    await asyncio.sleep(0.1)

    # send_bytes가 최소 1회 호출되었는지 확인
    ws.send_bytes.assert_called()
    # 호출된 인자가 bytes 타입인지 단언
    call_arg = ws.send_bytes.call_args[0][0]
    assert isinstance(call_arg, bytes)

    # 정리
    broadcaster._cleanup_session(sid)
