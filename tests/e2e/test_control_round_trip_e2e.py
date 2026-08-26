"""Control Round-trip E2E 검증 테스트 스위트.

검증 경로:
React / WebSocket Client
    ↓ (WebSocket Command 전송)
Backend WebSocket Server (UIWebSocketHub)
    ↓ (JSON Parse & Routing)
Dispatcher (TargetArchitectureUIServer.handle_command)
    ↓ (Command Validation & Execution)
Runtime (VSSF / Broker / OptionProgram / VMS)
    ↓ (Runtime State Change)
Snapshot Generation (TargetArchitectureUIServer.snapshot)
    ↓ (WebSocket Response / Broadcast)
Client UI State 반영
"""
import asyncio
import json
import sys
import unittest
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import websockets  # noqa: E402

from main import TradingSystem  # noqa: E402
from web_interface.server import TargetArchitectureUIServer, UIWebSocketHub  # noqa: E402


class TestControlRoundTripE2E(unittest.IsolatedAsyncioTestCase):
    """Control Round-trip E2E 테스트 스위트."""

    async def asyncSetUp(self):
        # 1. TradingSystem 인스턴스 생성 및 초기화
        self.config = {"broker_mode": "PAPER", "initial_capital": 50_000_000.0}
        self.system = TradingSystem(self.config)
        await self.system.initialize()

        # 2. 테스트 전용 독립 포트(8769)로 WebSocket Hub 기동
        self.port = 8769
        self.ui_server = TargetArchitectureUIServer(self.system)
        self.hub = UIWebSocketHub(
            adapter=self.ui_server,
            host="127.0.0.1",
            port=self.port,
            throttle_interval=0.05,
        )
        self.system.ui_server = self.ui_server
        self.system.ui_ws = self.hub
        await self.hub.start()
        self.uri = f"ws://127.0.0.1:{self.port}"

    async def asyncTearDown(self):
        await self.hub.stop()
        await self.system.shutdown()

    async def test_01_round_trip_command_a_margin_mode_control(self):
        """Command A — VSSF 증거금 모드 변경 (set_margin_mode: TIGHT) Round-trip E2E 검증."""
        async with websockets.connect(self.uri) as ws:
            # 1. 초기 스냅샷 수신 및 초기 Runtime 상태 확인
            init_msg = await ws.recv()
            init_snap = json.loads(init_msg)
            self.assertEqual(init_snap["type"], "ui_snapshot")
            self.assertEqual(self.system.vssf.control_snapshot()["margin_mode"], "NORMAL")

            # 2. WebSocket을 통해 Control Command 전송
            command = {"action": "set_margin_mode", "mode": "TIGHT"}
            await ws.send(json.dumps(command))

            # 3. Backend 응답 스냅샷 수신
            resp_msg = await ws.recv()
            resp_snap = json.loads(resp_msg)

            # 4. Dispatcher 실행 결과 검증
            self.assertEqual(resp_snap["command"]["status"], "APPLIED")
            self.assertEqual(resp_snap["command"]["action"], "set_margin_mode")
            self.assertIsNone(resp_snap["command"]["error"])

            # 5. 실제 Runtime (VSSF) 상태 변경 확인
            self.assertEqual(self.system.vssf.control_snapshot()["margin_mode"], "TIGHT")

            # 6. 스냅샷 데이터에 변경된 VSSF 컨트롤 상태가 UI로 정확히 반환되었는지 확인
            self.assertEqual(resp_snap["broker"]["vssf_control"]["margin_mode"], "TIGHT")

    async def test_02_round_trip_command_b_broker_connection_control(self):
        """Command B — Broker 통신 제어 (set_broker_connection: False) Round-trip E2E 검증."""
        async with websockets.connect(self.uri) as ws:
            # 1. 초기 스냅샷 수신 및 초기 Runtime 상태 확인
            await ws.recv()
            self.assertTrue(self.system.broker.is_connected())

            # 2. WebSocket을 통해 Broker 연결 해제 Command 전송
            command = {"action": "set_broker_connection", "connected": False}
            await ws.send(json.dumps(command))

            # 3. Backend 응답 스냅샷 수신
            resp_msg = await ws.recv()
            resp_snap = json.loads(resp_msg)

            # 4. Dispatcher 실행 결과 검증
            self.assertEqual(resp_snap["command"]["status"], "APPLIED")
            self.assertEqual(resp_snap["command"]["action"], "set_broker_connection")

            # 5. 실제 Runtime (Broker) 상태 변경 확인
            self.assertFalse(self.system.broker.is_connected())

            # 6. 스냅샷 데이터에 Broker 컨트롤 상태(connected: False)가 UI로 정확히 반환되었는지 확인
            self.assertFalse(resp_snap["broker"]["control"]["connected"])

            # 7. 재연결(connected: True) 복구 Round-trip 검증
            await ws.send(json.dumps({"action": "set_broker_connection", "connected": True}))
            restore_msg = await ws.recv()
            restore_snap = json.loads(restore_msg)
            self.assertEqual(restore_snap["command"]["status"], "APPLIED")
            self.assertTrue(self.system.broker.is_connected())
            self.assertTrue(restore_snap["broker"]["control"]["connected"])

    async def test_03_round_trip_command_c_strategy_toggle_and_market_regime(self):
        """Command C & D — OptionProgram 전략 토글 및 VMS 레짐 변경 Round-trip E2E 검증."""
        async with websockets.connect(self.uri) as ws:
            await ws.recv()  # 초기 스냅샷

            # (1) OptionProgram Track1 토글 (False로 비활성화)
            await ws.send(json.dumps({"action": "set_strategy_enabled", "track_id": "Track1", "enabled": False}))
            resp1 = json.loads(await ws.recv())
            self.assertEqual(resp1["command"]["status"], "APPLIED")
            self.assertFalse(self.system.op_runtime.enabled_strategies["Track1"])
            self.assertFalse(resp1["optionProgram"]["enabled_strategies"]["Track1"])

            # (2) VMS 시장 레짐을 CRISIS로 변경
            await ws.send(json.dumps({"action": "set_market_regime", "regime": "CRISIS"}))
            resp2 = json.loads(await ws.recv())
            self.assertEqual(resp2["command"]["status"], "APPLIED")
            self.assertEqual(self.system.vms.get_control_state()["market_regime"], "CRISIS")
            self.assertEqual(self.system.vms._market_regime, "CRISIS")


    async def test_04_round_trip_invalid_command_and_payload_validation(self):
        """Invalid Command / Payload — 검증 실패 및 에러 응답 Round-trip E2E 검증."""
        async with websockets.connect(self.uri) as ws:
            await ws.recv()  # 초기 스냅샷

            # Case A: 존재하지 않는 Unknown Action 전송
            invalid_cmd = {"action": "UNKNOWN_ACTION_999", "param": 123}
            await ws.send(json.dumps(invalid_cmd))
            resp_a = json.loads(await ws.recv())
            self.assertEqual(resp_a["command"]["status"], "REJECTED")
            self.assertEqual(resp_a["command"]["action"], "UNKNOWN_ACTION_999")
            self.assertIn("unknown action", resp_a["command"]["error"].lower())

            # Case B: 허용되지 않는 값(invalid choices) 전송
            invalid_payload = {"action": "set_margin_mode", "mode": "INVALID_MODE_XYZ"}
            await ws.send(json.dumps(invalid_payload))
            resp_b = json.loads(await ws.recv())
            self.assertEqual(resp_b["command"]["status"], "REJECTED")
            self.assertEqual(resp_b["command"]["action"], "set_margin_mode")
            self.assertIn("invalid value", resp_b["command"]["error"].lower())

            # Case C: 필수 파라미터 누락 전송
            missing_payload = {"action": "set_broker_connection"}
            await ws.send(json.dumps(missing_payload))
            resp_c = json.loads(await ws.recv())
            self.assertEqual(resp_c["command"]["status"], "REJECTED")
            self.assertIn("missing payload", resp_c["command"]["error"].lower())


if __name__ == "__main__":
    unittest.main()
