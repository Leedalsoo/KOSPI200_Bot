"""E2E Test: Broker 실패 후 Orchestrator 연속 실행 및 정상 체결 복구 경계 검증.

인과관계 및 검증 경계:
    RiskGate APPROVE
        ↓
    Broker.send_order() 실패 / 차단 (report is None)
        ↓
    해당 주문 ExecutionReport 없음 & Position/Margin 변동 없음 (APPROVE != FILLED)
        ↓
    Orchestrator(TradingSystem.run_loop) 중단 없이 다음 tick 연속 처리
        ↓
    다음 정상 Broker 호출에서 정상 체결(ExecutionReport) 및 Position/Margin mutation 복구

4대 시나리오:
- TEST A: Broker 실패 전 정상 APPROVE 기준선 확인
- TEST B: APPROVE -> Broker 실패 -> 해당 주문 미체결 및 상태 불변 실측
- TEST C: Broker 실패 후 Orchestrator가 중단 없이 다음 tick을 계속 처리(ticks_processed 증가 및 다음 tick RiskGate/Broker 재호출)함을 실측
- TEST D: 1번째 틱 Broker 실패(미체결) -> 2번째 틱 정상 복구 -> 정상 ExecutionReport 수령 및 Position/Margin mutation 발생 실측
"""
import unittest
from unittest.mock import MagicMock
import asyncio

from main import TradingSystem


class TestBrokerFailureOrchestratorContinuationE2E(unittest.TestCase):
    """Broker 실패 후 Orchestrator 연속 실행 및 복구 경계 E2E 검증."""

    def test_A_baseline_approve_and_broker_entry(self):
        """[TEST A] Broker 실패 전 정상 APPROVE 기준선 및 Broker.send_order() 진입 확인."""
        async def _run():
            system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 500_000_000.0})
            await system.initialize()

            # RiskGate 판정 및 Broker 호출 관측
            admit_results = []
            original_admit = system.op_runtime.risk_gate.admit_order

            def spy_admit(*args, **kwargs):
                res = original_admit(*args, **kwargs)
                admit_results.append(res)
                return res

            system.op_runtime.risk_gate.admit_order = spy_admit

            spy_send = MagicMock(side_effect=system.broker.send_order)
            system.broker.send_order = spy_send

            # 1 틱 실행
            await system.run_loop(max_ticks=1)

            # [실측 1] RiskGate APPROVE 판정 확인
            self.assertGreater(len(admit_results), 0)
            approved = [r for r in admit_results if r[0] is True]
            self.assertGreater(len(approved), 0, "RiskGate must APPROVE in normal state")
            for is_app, tok, rej in approved:
                self.assertTrue(is_app)
                self.assertIsNotNone(tok)
                self.assertIsNone(rej)

            # [실측 2] Orchestrator가 Broker.send_order() 호출 경로에 정상 진입했음 확인
            self.assertGreater(spy_send.call_count, 0)
            self.assertGreater(system.orders_routed, 0)

            await system.shutdown()

        asyncio.run(_run())

    def test_B_approve_with_broker_failure_no_execution(self):
        """[TEST B] APPROVE -> Broker 실패 -> 해당 주문 미체결(ExecutionReport 없음, Position/Margin 변동 없음) 실측."""
        async def _run():
            system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 500_000_000.0})
            await system.initialize()

            # Broker 실행 거부 동작 설정 (공식 제어 인터페이스 활용)
            system.broker.set_execution_behavior("REJECT")

            admit_results = []
            original_admit = system.op_runtime.risk_gate.admit_order

            def spy_admit(*args, **kwargs):
                res = original_admit(*args, **kwargs)
                admit_results.append(res)
                return res

            system.op_runtime.risk_gate.admit_order = spy_admit

            spy_send = MagicMock(side_effect=system.broker.send_order)
            system.broker.send_order = spy_send

            # 1 틱 실행
            await system.run_loop(max_ticks=1)

            # [실측 1] RiskGate 판정은 APPROVE였음
            approved = [r for r in admit_results if r[0] is True]
            self.assertGreater(len(approved), 0, "RiskGate must have approved the order")

            # [실측 2] Broker.send_order()는 실제로 호출되었음
            self.assertGreater(spy_send.call_count, 0, "Broker.send_order must have been invoked")

            # [실측 3] Broker 실패로 인해 ExecutionReport가 생성되지 않았음
            self.assertEqual(system.executions_handled, 0)
            self.assertEqual(len(system.vssf.execution_engine.reports), 0)
            self.assertEqual(len(system.op_runtime.received_execution_reports), 0)

            # [실측 4] Position 및 Margin 변동 없음
            self.assertEqual(len(system.vssf.account.get_positions()), 0)
            self.assertEqual(system.vssf.account.used_margin, 0.0)

            await system.shutdown()

        asyncio.run(_run())

    def test_C_orchestrator_continues_processing_subsequent_ticks_after_broker_failure(self):
        """[TEST C] Broker 실패 후에도 Orchestrator가 중단되지 않고 다음 tick을 계속 처리함을 직접 증명."""
        async def _run():
            system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 500_000_000.0})
            await system.initialize()

            # 1번째 틱 동안 Broker 실패 상태 유지
            system.broker.set_execution_behavior("REJECT")

            tick_count_admit = []
            original_admit = system.op_runtime.risk_gate.admit_order

            def spy_admit(*args, **kwargs):
                tick_count_admit.append(len(tick_count_admit) + 1)
                return original_admit(*args, **kwargs)

            system.op_runtime.risk_gate.admit_order = spy_admit

            spy_send = MagicMock(side_effect=system.broker.send_order)
            system.broker.send_order = spy_send

            # [단일 실행] 2개 틱 연속 실행
            await system.run_loop(max_ticks=2)

            # [직접 증거 1] Orchestrator가 2번째 틱까지 중단 없이 정상 처리 완료했음
            self.assertEqual(system.ticks_processed, 2, "Orchestrator must continue and process tick 2 despite broker failure")
            self.assertFalse(system._shutdown_event.is_set())

            # [직접 증거 2] 2번째 틱에서도 RiskGate 및 Broker 경로가 지속적으로 재평가/호출되었음
            self.assertGreater(len(tick_count_admit), 1, "RiskGate must be invoked across multiple ticks")
            self.assertGreater(spy_send.call_count, 1, "Broker must continue to receive orders on subsequent ticks")

            await system.shutdown()

        asyncio.run(_run())

    def test_D_recovery_and_normal_execution_after_broker_failure(self):
        """[TEST D] 1번째 틱 Broker 실패 -> 2번째 틱 정상 복구 -> 정상 ExecutionReport 생성 및 Position/Margin mutation 발생 실측."""
        async def _run():
            system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 500_000_000.0})
            await system.initialize()

            # Phase 1: 1번째 틱 Broker 실패 설정
            system.broker.set_execution_behavior("REJECT")
            await system.run_loop(max_ticks=1)

            # Phase 1 상태 실측: 0 체결, 0 포지션, 0 마진
            self.assertEqual(system.ticks_processed, 1)
            self.assertEqual(system.executions_handled, 0, "Phase 1: executions_handled must be 0")
            self.assertEqual(len(system.vssf.account.get_positions()), 0, "Phase 1: No positions")
            self.assertEqual(system.vssf.account.used_margin, 0.0, "Phase 1: Used margin must be 0")

            # Phase 2: Broker를 NORMAL(정상) 상태로 복구
            system.broker.set_execution_behavior("NORMAL")

            # Phase 3: 동일 세션에서 2번째 틱 실행
            await system.run_loop(max_ticks=2)
            self.assertEqual(system.ticks_processed, 2)

            # Phase 3 상태 실측: 복구 후 정상 체결 수령 및 포지션/마진 mutation 발생
            self.assertGreater(system.executions_handled, 0, "Phase 3: executions_handled must increase after recovery")
            self.assertGreater(len(system.vssf.execution_engine.reports), 0, "Phase 3: ExecutionReport must be generated")
            self.assertGreater(len(system.vssf.account.get_positions()), 0, "Phase 3: Position must be created")
            self.assertGreater(system.vssf.account.used_margin, 0.0, "Phase 3: Used margin must increase")

            await system.shutdown()

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
