"""E2E Test: Orchestrator 내부 실제 RiskGate 판정 <-> rejection_reason <-> Broker 호출 결과의 단일 실행 연결 검증.

단일 실행 흐름:
    TradingSystem.run_loop(1)
            ↓
    OptionProgramRuntime.process_tick()
            ↓
    RiskGate.admit_order()
            ↓
    [APPROVE 또는 DENY]
            ↓
    rejection_reason
            ↓
    Orchestrator의 실제 Broker 호출 여부
            ↓
    Broker.send_order() 호출 결과

3대 핵심 시나리오:
- TEST A: 단일 run_loop(1) 실행 내 APPROVE 판정 -> Broker.send_order() 실제 호출(call_count > 0) -> CanonicalExecutionReport 체결 수령 1:1 연결 실측
- TEST B: 단일 run_loop(1) 실행 내 DENY (EXCEEDED_MAX_DAILY_LOSS) 판정 -> rejection_reason 포착 -> Broker.send_order() 0회(call_count == 0) 미호출 1:1 연결 실측
- TEST C: 단일 run_loop(1) 실행 내 DENY (EXCEEDED_MAX_ORDER_QTY) 판정 -> rejection_reason 포착 -> Broker.send_order() 0회(call_count == 0) 미호출 1:1 연결 실측
"""
import unittest
from unittest.mock import MagicMock
import asyncio

from main import TradingSystem


class TestOrchestratorRiskGateBrokerSingleExecutionFlowE2E(unittest.TestCase):
    """단일 TradingSystem.run_loop(1) 실행 내 RiskGate 판정 <-> rejection_reason <-> Broker 호출 결과 연결 E2E 검증."""

    def test_A_single_run_loop_approve_to_broker_execution(self):
        """[TEST A] 단일 run_loop(1) 실행 -> RiskGate APPROVE -> Broker.send_order() 호출(call_count > 0) 및 체결 수령 실측."""
        async def _run():
            system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 500_000_000.0})
            await system.initialize()

            # 1. RiskGate.admit_order와 Broker.send_order에 spy 계측 설치
            original_admit = system.op_runtime.risk_gate.admit_order
            admit_results = []

            def spy_admit(*args, **kwargs):
                res = original_admit(*args, **kwargs)
                admit_results.append(res)  # (is_approved, token, rej_reason)
                return res

            system.op_runtime.risk_gate.admit_order = spy_admit

            original_send = system.broker.send_order
            spy_send = MagicMock(side_effect=original_send)
            system.broker.send_order = spy_send

            # 2. [단일 실행] Orchestrator 1 틱 실행
            await system.run_loop(max_ticks=1)

            # 3. [단일 실행 흐름 실측 1] RiskGate.admit_order()가 런타임 내부에서 실제 실행되어 APPROVE를 반환했는지 확인
            self.assertGreater(len(admit_results), 0, "RiskGate.admit_order must be invoked during run_loop")
            approved_results = [r for r in admit_results if r[0] is True]
            self.assertGreater(len(approved_results), 0, "At least one order must be APPROVED by RiskGate")
            for is_app, token, rej in approved_results:
                self.assertTrue(is_app)
                self.assertIsNotNone(token)
                self.assertIsNone(rej)

            # 4. [단일 실행 흐름 실측 2] APPROVE 판정에 대응하여 Orchestrator가 Broker.send_order()를 실제로 호출했는지 확인
            self.assertEqual(spy_send.call_count, len(approved_results), "Broker.send_order call count must exactly match approved orders")
            self.assertGreater(spy_send.call_count, 0)

            # 5. [단일 실행 흐름 실측 3] Broker 체결 결과가 Orchestrator와 VSSF에 실제 반영되었는지 확인
            self.assertGreater(system.executions_handled, 0)
            self.assertGreater(len(system.vssf.execution_engine.reports), 0)
            self.assertGreater(len(system.vssf.account.get_positions()), 0)

            await system.shutdown()

        asyncio.run(_run())

    def test_B_single_run_loop_daily_loss_deny_to_broker_suppression(self):
        """[TEST B] 단일 run_loop(1) 실행 -> RiskGate DENY (EXCEEDED_MAX_DAILY_LOSS) -> Broker.send_order() 0회 미호출 실측."""
        async def _run():
            system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 500_000_000.0})
            await system.initialize()
            system.op_runtime.risk_config.max_daily_loss_krw = 10_000_000.0

            # 1. 일일 손실 한도 초과 주입 (-1500만원 손실)
            system.vssf.account.realized_pnl = -15_000_000.0

            # 2. RiskGate.admit_order와 Broker.send_order에 spy 계측 설치
            original_admit = system.op_runtime.risk_gate.admit_order
            admit_results = []

            def spy_admit(*args, **kwargs):
                res = original_admit(*args, **kwargs)
                admit_results.append(res)
                return res

            system.op_runtime.risk_gate.admit_order = spy_admit

            original_send = system.broker.send_order
            spy_send = MagicMock(side_effect=original_send)
            system.broker.send_order = spy_send

            # 3. [단일 실행] Orchestrator 1 틱 실행
            await system.run_loop(max_ticks=1)

            # 4. [단일 실행 흐름 실측 1] RiskGate.admit_order()가 런타임 내부에서 실제 실행되어 DENY 및 일일손실 거부사유를 반환했는지 확인
            self.assertGreater(len(admit_results), 0, "RiskGate.admit_order must be invoked during run_loop")
            for is_app, token, rej in admit_results:
                self.assertFalse(is_app, "All orders must be DENIED under max daily loss breach")
                self.assertIsNone(token, "Token must be None on DENY")
                self.assertIsNotNone(rej)
                self.assertIn("EXCEEDED_MAX_DAILY_LOSS", rej)

            # 5. [단일 실행 흐름 실측 2] DENY 판정에 대응하여 Orchestrator가 Broker.send_order()를 0회 호출했는지 직접 계측
            self.assertEqual(spy_send.call_count, 0, "Broker.send_order must be called 0 times on DENY")
            self.assertEqual(system.orders_routed, 0)
            self.assertEqual(system.executions_handled, 0)

            await system.shutdown()

        asyncio.run(_run())

    def test_C_single_run_loop_order_qty_deny_to_broker_suppression(self):
        """[TEST C] 단일 run_loop(1) 실행 -> RiskGate DENY (EXCEEDED_MAX_ORDER_QTY) -> Broker.send_order() 0회 미호출 실측."""
        async def _run():
            system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 500_000_000.0})
            await system.initialize()
            system.op_runtime.risk_config.max_order_qty = 0  # 1회 최대 수량 0으로 제한

            # 1. RiskGate.admit_order와 Broker.send_order에 spy 계측 설치
            original_admit = system.op_runtime.risk_gate.admit_order
            admit_results = []

            def spy_admit(*args, **kwargs):
                res = original_admit(*args, **kwargs)
                admit_results.append(res)
                return res

            system.op_runtime.risk_gate.admit_order = spy_admit

            original_send = system.broker.send_order
            spy_send = MagicMock(side_effect=original_send)
            system.broker.send_order = spy_send

            # 2. [단일 실행] Orchestrator 1 틱 실행
            await system.run_loop(max_ticks=1)

            # 3. [단일 실행 흐름 실측 1] RiskGate.admit_order()가 런타임 내부에서 실제 실행되어 DENY 및 수량초과 거부사유를 반환했는지 확인
            self.assertGreater(len(admit_results), 0, "RiskGate.admit_order must be invoked during run_loop")
            for is_app, token, rej in admit_results:
                self.assertFalse(is_app, "All orders must be DENIED under max order qty breach")
                self.assertIsNone(token, "Token must be None on DENY")
                self.assertIsNotNone(rej)
                self.assertIn("EXCEEDED_MAX_ORDER_QTY", rej)

            # 4. [단일 실행 흐름 실측 2] DENY 판정에 대응하여 Orchestrator가 Broker.send_order()를 0회 호출했는지 직접 계측
            self.assertEqual(spy_send.call_count, 0, "Broker.send_order must be called 0 times on DENY")
            self.assertEqual(system.orders_routed, 0)
            self.assertEqual(system.executions_handled, 0)

            await system.shutdown()

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
