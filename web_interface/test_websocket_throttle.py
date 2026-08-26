"""WebSocket Broadcast Throttle 단위 테스트.

검증 항목:
- Test 1: 최초 broadcast 정상 전송
- Test 2: 짧은 간격 다중 호출 시 throttle 적용 (전송 횟수 제한)
- Test 3: throttle interval 경과 후 재전송 정상 동작
- Test 4: throttle 이후 전송 시 최신 snapshot 반영 확인
- Test 5: send 실패 client(dead client) 정상 제거
- Test 6: broadcast skip 시 trading pipeline 비차단(즉각 반환) 확인
"""
import asyncio
import sys
import time
import unittest
from pathlib import Path
from typing import Any, Dict

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from web_interface.server import UIWebSocketHub  # noqa: E402



class MockClient:
    """테스트용 WebSocket Client Mock."""

    def __init__(self, should_fail: bool = False):
        self.sent_messages = []
        self.should_fail = should_fail

    async def send(self, message: str):
        if self.should_fail:
            raise ConnectionResetError("Client disconnected")
        self.sent_messages.append(message)


class DummyAdapter:
    """테스트용 Snapshot Adapter."""

    def __init__(self):
        self.seq_id = 0

    def snapshot(self) -> Dict[str, Any]:
        return {"type": "ui_snapshot", "seq_id": self.seq_id}


class TestWebSocketThrottle(unittest.IsolatedAsyncioTestCase):
    """UIWebSocketHub Broadcast Throttle 테스트 스위트."""

    async def asyncSetUp(self):
        self.adapter = DummyAdapter()
        self.hub = UIWebSocketHub(
            adapter=self.adapter,
            host="127.0.0.1",
            port=8765,
            throttle_interval=0.05,  # 50ms (20 FPS)
        )

    async def test_01_initial_broadcast(self):
        """Test 1 — client가 연결된 상태에서 최초 broadcast가 정상적으로 전송되는지 확인."""
        client = MockClient()
        self.hub.clients.add(client)

        self.assertEqual(len(client.sent_messages), 0)
        await self.hub.broadcast()

        self.assertEqual(len(client.sent_messages), 1)
        self.assertIn('"seq_id":0', client.sent_messages[0])

    async def test_02_throttle_multiple_rapid_calls(self):
        """Test 2 — 짧은 시간 안에 broadcast()를 여러 번 호출했을 때 실제 send 횟수가 1회로 제한되는지 확인."""
        client = MockClient()
        self.hub.clients.add(client)

        # 짧은 간격으로 4회 연속 호출
        await self.hub.broadcast()
        await self.hub.broadcast()
        await self.hub.broadcast()
        await self.hub.broadcast()

        # throttle에 의해 첫 1회만 전송되고 나머지는 skip되어야 함
        self.assertEqual(len(client.sent_messages), 1)

    async def test_03_retransmission_after_throttle_interval(self):
        """Test 3 — throttle interval이 지난 후 broadcast()를 호출하면 정상 재전송되는지 확인."""
        client = MockClient()
        self.hub.clients.add(client)

        await self.hub.broadcast()
        self.assertEqual(len(client.sent_messages), 1)

        # interval(50ms) 경과 대기
        await asyncio.sleep(0.06)

        await self.hub.broadcast()
        self.assertEqual(len(client.sent_messages), 2)

    async def test_04_delivers_latest_snapshot(self):
        """Test 4 — throttle 중간에 snapshot 내용이 변경되었을 때 다음 실제 broadcast에서 최신 snapshot이 전송되는지 확인."""
        client = MockClient()
        self.hub.clients.add(client)

        self.adapter.seq_id = 100
        await self.hub.broadcast()
        self.assertEqual(len(client.sent_messages), 1)
        self.assertIn('"seq_id":100', client.sent_messages[0])

        # throttle 기간 중 데이터 업데이트 및 broadcast 시도 (skip됨)
        self.adapter.seq_id = 200
        await self.hub.broadcast()
        self.assertEqual(len(client.sent_messages), 1)

        # 추가 데이터 갱신 후 interval 경과
        self.adapter.seq_id = 300
        await asyncio.sleep(0.06)

        await self.hub.broadcast()
        self.assertEqual(len(client.sent_messages), 2)
        # 마지막 전송 메시지에 가장 최신 seq_id(300)가 포함되어야 함
        self.assertIn('"seq_id":300', client.sent_messages[1])

    async def test_05_dead_client_removal(self):
        """Test 5 — send 중 예외가 발생하는 client가 있을 경우 dead client가 clients 집합에서 정상 제거되는지 확인."""
        alive_client = MockClient(should_fail=False)
        dead_client = MockClient(should_fail=True)

        self.hub.clients.add(alive_client)
        self.hub.clients.add(dead_client)
        self.assertEqual(len(self.hub.clients), 2)

        await self.hub.broadcast()

        # 정상 client는 수신하고, dead client는 clients 집합에서 제거됨
        self.assertEqual(len(alive_client.sent_messages), 1)
        self.assertEqual(len(self.hub.clients), 1)
        self.assertIn(alive_client, self.hub.clients)
        self.assertNotIn(dead_client, self.hub.clients)

    async def test_06_non_blocking_trading_pipeline(self):
        """Test 6 — throttle 스킵 시 sleep 대기 없이 즉각 반환(비차단)되는지 확인."""
        client = MockClient()
        self.hub.clients.add(client)

        await self.hub.broadcast()

        # 100회 연속 스킵 호출 시간 측정
        start_time = time.perf_counter()
        for _ in range(100):
            await self.hub.broadcast()
        elapsed = time.perf_counter() - start_time

        # 100회 호출이 blocking 없이 수 밀리초 이내(0.01초 미만)에 완료되어야 함
        self.assertLess(elapsed, 0.01, f"broadcast throttle should be non-blocking, took {elapsed:.4f}s")


if __name__ == "__main__":
    unittest.main()
