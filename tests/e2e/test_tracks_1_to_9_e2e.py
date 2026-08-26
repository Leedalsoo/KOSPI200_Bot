"""Track 1~9 최종 조정 및 통합 E2E 검증 테스트 스위트.

검증 대상:
Track 1 (Trend-Following Fence)
Track 2 (Asymmetric Volatility Trap)
Track 3 (Synthetic Arbitrage)
Track 4 (Scalping Basecamp)
Track 5 (Mean Reversion & Gap Divergence)
Track 6 (Dynamic Volatility Insurance)
Track 7 (Calendar Spread Insurance)
Track 8 (Tail Risk Protection)
Track 9 (Overnight Hedge & OTM Insurance)

검증 경로:
Track 등록 ➔ 활성화 상태 ➔ Runtime 평가 ➔ Signal/Order ➔ RiskGate ➔ Broker ➔ VSSF ➔ UI Snapshot
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
from shared.contracts.canonical import CanonicalMarketTick  # noqa: E402
from web_interface.server import TargetArchitectureUIServer, UIWebSocketHub  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_tracks_1_to_9_e2e")


class TestTracks1To9E2E(unittest.IsolatedAsyncioTestCase):
    """Track 1~9 통합 조정 및 E2E 테스트 스위트."""

    async def asyncSetUp(self):
        self.config = {"broker_mode": "PAPER", "initial_capital": 50_000_000.0}
        self.system = TradingSystem(self.config)
        await self.system.initialize()

        self.port = 8773
        self.ui_server = TargetArchitectureUIServer(self.system)
        self.hub = UIWebSocketHub(
            adapter=self.ui_server,
            host="127.0.0.1",
            port=self.port,
            throttle_interval=0.01,
        )
        self.system.ui_server = self.ui_server
        self.system.ui_ws = self.hub
        await self.hub.start()
        self.uri = f"ws://127.0.0.1:{self.port}"

    async def asyncTearDown(self):
        await self.hub.stop()
        await self.system.shutdown()

    def test_01_all_tracks_registration_and_metadata(self):
        """Track 1~9가 OptionProgramRuntime에 모두 등록되어 있고 초기 활성화 상태인지 검증."""
        op = self.system.op_runtime
        self.assertIsNotNone(op)

        registered_tracks = [getattr(st, "name", st.__class__.__name__) for st in op.strategies]
        expected_tracks = [f"Track{i}" for i in range(1, 10)]

        for track_id in expected_tracks:
            self.assertIn(track_id, registered_tracks, f"{track_id}가 등록되어 있어야 함")
            self.assertTrue(op.enabled_strategies.get(track_id, False), f"{track_id}는 기본 활성화(True)여야 함")
            self.assertIn(track_id, op.strategy_metrics, f"{track_id} 메트릭이 초기화되어 있어야 함")

    def test_02_individual_track_evaluation_no_exceptions(self):
        """Track 1~9 각각에 대해 합성 틱을 공급하여 예외 없이 평가(Evaluation)가 실행되는지 개별 검증."""
        op = self.system.op_runtime
        tick = CanonicalMarketTick(
            timestamp="2026-08-23 09:00:00.000",
            underlying_price=350.0,
            bid_price=349.9,
            ask_price=350.1,
            last_price=350.0,
            volume=1000,
            seq_id=1,
        )

        for track_id in [f"Track{i}" for i in range(1, 10)]:
            # 단일 Track만 활성화하고 나머지 비활성화
            for t in [f"Track{j}" for j in range(1, 10)]:
                op.enabled_strategies[t] = (t == track_id)

            initial_eval_count = op.strategy_metrics[track_id]["ticks_evaluated"]
            initial_exceptions = op.strategy_metrics[track_id]["exceptions"]

            # 틱 평가 실행
            commands = op.process_tick(tick)

            # 검증: 평가 카운트 1 증가, 예외 0개, 명령 리스트 반환
            self.assertEqual(op.strategy_metrics[track_id]["ticks_evaluated"], initial_eval_count + 1)
            self.assertEqual(op.strategy_metrics[track_id]["exceptions"], initial_exceptions)
            self.assertIsInstance(commands, list)

    async def test_03_integrated_tracks_simultaneous_execution(self):
        """Track 1~9 동시 활성화 하에서 100틱 스트림 가동 시 충돌 없이 전 Track이 평가되고 메트릭이 누적되는지 검증."""
        target_ticks = 100

        # 모든 Track 활성화 확인
        for i in range(1, 10):
            self.system.op_runtime.enabled_strategies[f"Track{i}"] = True

        # 메인 파이프라인 가동 (100틱)
        await self.system.run_loop(max_ticks=target_ticks)

        self.assertEqual(self.system.ticks_processed, target_ticks)

        # Track 1~9 전수 평가 실측 결과 확인
        for i in range(1, 10):
            t_name = f"Track{i}"
            metric = self.system.op_runtime.strategy_metrics[t_name]
            self.assertEqual(metric["ticks_evaluated"], target_ticks, f"{t_name}은 100틱 모두 평가되어야 함")
            self.assertEqual(metric["exceptions"], 0, f"{t_name}에서 예외가 발생하지 않아야 함")

        # 스냅샷 생성 및 무결성 확인
        snap = self.ui_server.snapshot()
        self.assertEqual(snap["type"], "ui_snapshot")
        self.assertEqual(len(snap["optionProgram"]["enabled_strategies"]), 9)
        self.assertEqual(len(snap["optionProgram"]["strategy_metrics"]), 9)

    async def test_04_track_control_toggle_and_ui_snapshot_sync(self):
        """Control Command를 통해 Track 비활성화/활성화 시 Runtime 평가 스킵 및 UI 스냅샷 동기화 E2E 검증."""
        async with websockets.connect(self.uri) as ws:
            await ws.recv()  # 초기 스냅샷

            # 1. Track1 비활성화 명령 전송
            await ws.send(json.dumps({"action": "set_strategy_enabled", "track_id": "Track1", "enabled": False}))
            resp_snap1 = json.loads(await ws.recv())

            self.assertEqual(resp_snap1["command"]["status"], "APPLIED")
            self.assertFalse(self.system.op_runtime.enabled_strategies["Track1"])
            self.assertFalse(resp_snap1["optionProgram"]["enabled_strategies"]["Track1"])

            # 2. 10틱 실행 후 Track1은 평가되지 않고(0), Track2~9만 평가되는지 확인
            t1_before = self.system.op_runtime.strategy_metrics["Track1"]["ticks_evaluated"]
            t2_before = self.system.op_runtime.strategy_metrics["Track2"]["ticks_evaluated"]

            tick = CanonicalMarketTick(
                timestamp="2026-08-23 09:05:00.000",
                underlying_price=351.0,
                bid_price=350.9,
                ask_price=351.1,
                last_price=351.0,
                volume=1000,
                seq_id=999,
            )
            self.system.op_runtime.process_tick(tick)

            t1_after = self.system.op_runtime.strategy_metrics["Track1"]["ticks_evaluated"]
            t2_after = self.system.op_runtime.strategy_metrics["Track2"]["ticks_evaluated"]

            self.assertEqual(t1_after, t1_before, "비활성화된 Track1은 평가가 스킵되어야 함")
            self.assertEqual(t2_after, t2_before + 1, "활성화된 Track2는 평가되어야 함")



if __name__ == "__main__":
    unittest.main()
