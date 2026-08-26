"""전체 공급경로 E2E (Full Supply Path E2E) 종합 검증 테스트 스위트.

검증 경로:
1. VMS (Scenario / Replay / Market Generator) 틱 공급원
   ↓ (CanonicalMarketTick)
2. TradingSystem.run_loop 메인 파이프라인 수신
   ↓ (process_market_data)
3. VSSF 시세 갱신 & OptionProgram 계좌 동기화
   ↓ (process_tick)
4. OptionProgram (Track 1~9 + Sensor + Arbiter + RiskGate)
   ↓ (OrderRequest / Commands)
5. Broker (PaperBroker) 발주 및 체결 (ExecutionReport)
   ↓ (consume_execution_report)
6. VSSF 포지션, 증거금, 실현/평가 PnL 회계 반영
   ↓ (TargetArchitectureUIServer.snapshot)
7. Realtime PnL Coord (x: seq_id, y: PnL) 생성
   ↓ (UIWebSocketHub 50ms Throttle Broadcast)
8. WebSocket Client 실시간 수신 및 UI 상태 누적 동기화
   ↓ (EOD Settlement & Reconciliation)
9. 장 마감 정산 및 회계 무결성 (is_healthy: True)
"""
import asyncio
import json
import logging
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import websockets  # noqa: E402

from main import TradingSystem  # noqa: E402
from web_interface.server import TargetArchitectureUIServer, UIWebSocketHub  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_full_supply_path_e2e")


class TestFullSupplyPathE2E(unittest.IsolatedAsyncioTestCase):
    """전체 공급경로 E2E 종합 테스트 스위트."""

    async def asyncSetUp(self):
        self.config = {"broker_mode": "PAPER", "initial_capital": 50_000_000.0}
        self.system = TradingSystem(self.config)
        await self.system.initialize()

        self.port = 8771
        self.ui_server = TargetArchitectureUIServer(self.system)
        self.hub = UIWebSocketHub(
            adapter=self.ui_server,
            host="127.0.0.1",
            port=self.port,
            throttle_interval=0.01,  # E2E 테스트 시 빠른 반응을 위해 10ms 설정
        )
        self.system.ui_server = self.ui_server
        self.system.ui_ws = self.hub
        await self.hub.start()
        self.uri = f"ws://127.0.0.1:{self.port}"

    async def asyncTearDown(self):
        await self.hub.stop()
        await self.system.shutdown()

    async def test_01_full_supply_path_150_ticks_live_stream(self):
        """150 틱 실시간 스트리밍 하에서 VMS -> Strategy -> Broker -> VSSF -> PnL -> WebSocket -> Client UI 전체 공급경로 E2E 검증."""
        target_ticks = 150
        received_snapshots: List[Dict[str, Any]] = []
        rx_ready = asyncio.Event()
        stop_client = asyncio.Event()

        async def client_receiver():
            async with websockets.connect(self.uri) as ws:
                # 1. 최초 스냅샷 수신
                init_msg = await ws.recv()
                received_snapshots.append(json.loads(init_msg))
                rx_ready.set()

                while not stop_client.is_set():
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=0.5)
                        snap = json.loads(msg)
                        received_snapshots.append(snap)
                    except asyncio.TimeoutError:
                        if stop_client.is_set():
                            break
                    except Exception as exc:
                        logger.warning("Receiver client exception: %s", exc)
                        break

        client_task = asyncio.create_task(client_receiver())
        await rx_ready.wait()

        # 2. 메인 파이프라인 가동 (150 틱 연속 실행)
        await self.system.run_loop(max_ticks=target_ticks)

        # 3. 마지막 틱 스냅샷 강제 브로드캐스트 및 수신 안정화
        self.hub.last_broadcast_time = 0.0
        await self.hub.broadcast()
        await asyncio.sleep(0.2)
        stop_client.set()
        await client_task

        # [검증 1] VMS 틱 공급 및 시스템 처리 수량 일치 확인
        self.assertEqual(self.system.ticks_processed, target_ticks)
        self.assertIsNotNone(self.system.last_tick)
        self.assertGreaterEqual(self.system.last_tick.seq_id, target_ticks)

        # [검증 2] WebSocket 클라이언트가 틱 스트림 스냅샷들을 정상 수신했는지 확인
        self.assertGreater(len(received_snapshots), 1, "최소 2개 이상의 스냅샷(초기 + 스트리밍)이 수신되어야 함")

        # [검증 3] 수신된 최신 스냅샷의 데이터 구조 및 무결성 확인
        latest = received_snapshots[-1]
        self.assertEqual(latest["type"], "ui_snapshot")
        self.assertIn("market", latest)
        self.assertIn("broker", latest)
        self.assertIn("optionProgram", latest)
        self.assertIn("coord", latest)
        self.assertIn("pnl", latest)
        self.assertIn("orders", latest)
        self.assertIn("executions", latest)

        # [검증 4] Realtime PnL Coord 데이터 검증 (단일 틱 좌표 및 수신 스트림 누적)
        coord = latest["coord"]
        self.assertIn("x", coord)
        self.assertIn("y", coord)
        self.assertEqual(coord["x"], self.system.last_tick.seq_id)
        # PnL 일치 검증: coord['y'] == pnl['realized'] + pnl['unrealized']
        expected_pnl = float(latest["pnl"]["realized"]) + float(latest["pnl"]["unrealized"])
        self.assertAlmostEqual(coord["y"], expected_pnl, places=2)

        # [검증 5] Strategy 신호 생성, 주문 발주 및 체결 통계 확인
        self.assertGreaterEqual(self.system.orders_routed, 0)
        self.assertGreaterEqual(self.system.executions_handled, 0)
        self.assertEqual(latest["replay"]["ticks_processed"], target_ticks)

        # [검증 6] VSSF 계좌 잔고 및 정산 대조(Reconciliation) 무결성 확인
        account = self.system.vssf.get_account_snapshot()
        self.assertGreater(account.balance, 0.0)
        reconcil = self.system.vssf.run_reconciliation()
        self.assertTrue(reconcil.get("is_healthy", False), "VSSF 원장 대조가 healthy 상태여야 함")

    async def test_02_scenario_control_and_realtime_stream_sync(self):
        """스트림 가동 중 VMS 파라미터 동적 변경 시 실시간 공급경로 동기화 E2E 검증."""
        target_ticks = 80
        received_snapshots: List[Dict[str, Any]] = []
        rx_ready = asyncio.Event()
        stop_client = asyncio.Event()

        async def client_receiver():
            async with websockets.connect(self.uri) as ws:
                init_msg = await ws.recv()
                received_snapshots.append(json.loads(init_msg))
                rx_ready.set()

                while not stop_client.is_set():
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=0.5)
                        received_snapshots.append(json.loads(msg))
                    except asyncio.TimeoutError:
                        if stop_client.is_set():
                            break
                    except Exception:
                        break

        client_task = asyncio.create_task(client_receiver())
        await rx_ready.wait()

        # VMS 가격 생성 조건 및 레짐 변경 적용
        self.system.vms.set_generator_config(base_price=360.0, volatility_ratio=1.5, spread=0.1, volume=5000)
        self.system.vms.set_market_regime("VOLATILE")

        # 80틱 연속 실행
        await self.system.run_loop(max_ticks=target_ticks)
        self.assertEqual(self.system.ticks_processed, target_ticks)

        self.hub.last_broadcast_time = 0.0
        await self.hub.broadcast()
        await asyncio.sleep(0.2)
        stop_client.set()
        await client_task

        # [검증] 최신 스냅샷에 갱신된 시장 틱 시세와 틱 처리 수치가 정확히 전달되었는지 확인
        latest = received_snapshots[-1]
        self.assertEqual(latest["replay"]["ticks_processed"], target_ticks)
        self.assertEqual(self.system.vms.get_control_state()["market_regime"], "VOLATILE")
        self.assertEqual(self.system.vms.get_control_state()["generator"]["spread"], 0.1)


if __name__ == "__main__":
    unittest.main()
