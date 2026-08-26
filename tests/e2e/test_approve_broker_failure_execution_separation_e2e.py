"""E2E Test: APPROVE 주문의 Broker 호출 실패/예외 발생 시 RiskGate 승인 결과와 실제 체결 결과의 엄격한 분리 및 비혼동 검증.

핵심 인과관계:
    RiskGate APPROVE
        ↓
    Orchestrator가 Broker.send_order() 호출
        ↓
    Broker 호출에서 실패/예외 발생
        ↓
    실제 체결(ExecutionReport) 미발생
        ↓
    "RiskGate 승인(APPROVE)"과 "실제 체결 성공(FILLED)"의 명확한 상태 분리

3대 시나리오:
- TEST A: APPROVE -> 정상 Broker 호출 -> 실제 ExecutionReport 수령 및 Position/Account mutation 발생 (정상 기준선)
- TEST B: APPROVE -> Broker.send_order() 예외 발생 -> ExecutionReport 미생성, executions_handled=0, Position/Account mutation=0 실측
- TEST C: Broker 실패 후 risk_decision(APPROVE) != broker_result(EXCEPTION) != execution_result(NO_EXECUTION) 상태 분리 및 APPROVE!=FILLED 비혼동 검증
"""
import unittest
from unittest.mock import MagicMock
import asyncio

from main import TradingSystem


class TestApproveBrokerFailureExecutionSeparationE2E(unittest.TestCase):
    """RiskGate 승인(APPROVE)과 Broker 체결(FILLED) 결과의 엄격한 상태 분리 E2E 검증."""

    def test_A_approve_and_normal_broker_execution_baseline(self):
        """[TEST A] APPROVE + 정상 Broker 호출 -> ExecutionReport 생성 및 Position/Account mutation 발생 (정상 기준선)."""
        async def _run():
            system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 500_000_000.0})
            await system.initialize()

            # 1. RiskGate.admit_order 실시간 관측용 spy 설치
            original_admit = system.op_runtime.risk_gate.admit_order
            admit_results = []

            def spy_admit(*args, **kwargs):
                res = original_admit(*args, **kwargs)
                admit_results.append(res)
                return res

            system.op_runtime.risk_gate.admit_order = spy_admit

            # 2. Broker.send_order 호출 관측용 spy 설치
            original_send = system.broker.send_order
            spy_send = MagicMock(side_effect=original_send)
            system.broker.send_order = spy_send

            # 3. [단일 실행] Orchestrator 1 틱 실행
            await system.run_loop(max_ticks=1)

            # 4. [관측 1] RiskGate 판정이 APPROVE였음 확인
            self.assertGreater(len(admit_results), 0)
            approved_list = [r for r in admit_results if r[0] is True]
            self.assertGreater(len(approved_list), 0, "RiskGate must directly APPROVE orders in normal state")
            for is_app, token, rej in approved_list:
                self.assertTrue(is_app)
                self.assertIsNotNone(token)
                self.assertIsNone(rej)

            # 5. [관측 2] Broker.send_order()가 정상 호출 완료되었음 확인
            self.assertGreater(spy_send.call_count, 0)
            self.assertEqual(spy_send.call_count, len(approved_list))

            # 6. [관측 3] 실제 ExecutionReport 수신 및 Position/Account mutation 발생 확인
            self.assertGreater(system.executions_handled, 0)
            self.assertGreater(len(system.vssf.execution_engine.reports), 0)
            self.assertGreater(len(system.vssf.account.get_positions()), 0)
            self.assertGreater(system.vssf.account.used_margin, 0.0)

            await system.shutdown()

        asyncio.run(_run())

    def test_B_approve_with_broker_exception_suppresses_execution(self):
        """[TEST B] APPROVE + Broker 예외 발생 -> ExecutionReport 미생성, executions_handled=0, Position/Account mutation=0 실측."""
        async def _run():
            system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 500_000_000.0})
            await system.initialize()

            # 1. RiskGate.admit_order 실시간 관측용 spy 설치
            original_admit = system.op_runtime.risk_gate.admit_order
            admit_results = []

            def spy_admit(*args, **kwargs):
                res = original_admit(*args, **kwargs)
                admit_results.append(res)
                return res

            system.op_runtime.risk_gate.admit_order = spy_admit

            # 2. Broker.send_order에 의도적 예외(Fault Injection) 주입
            broker_exception = ConnectionError("Broker Gateway Connection Timeout")
            spy_send = MagicMock(side_effect=broker_exception)
            system.broker.send_order = spy_send

            # 초기 VSSF 상태 스냅샷
            pos_initial = dict(system.vssf.account.get_positions())
            bal_initial = system.vssf.account.balance
            margin_initial = system.vssf.account.used_margin
            reports_initial = len(system.vssf.execution_engine.reports)

            # 3. [단일 실행] Orchestrator 1 틱 실행 및 예외 발생 확인
            exception_caught = None
            try:
                await system.run_loop(max_ticks=1)
            except ConnectionError as exc:
                exception_caught = exc

            # 4. [관측 1: RiskGate] RiskGate는 정상적으로 APPROVE를 판정하고 Token을 발급했음 확인
            self.assertGreater(len(admit_results), 0)
            approved_list = [r for r in admit_results if r[0] is True]
            self.assertGreater(len(approved_list), 0, "RiskGate must have APPROVED the order before broker invocation")
            for is_app, token, rej in approved_list:
                self.assertTrue(is_app)
                self.assertIsNotNone(token)
                self.assertIsNone(rej)

            # 5. [관측 2: Broker] Broker.send_order()가 실제 호출되었고 의도한 ConnectionError가 발생했음 확인
            self.assertGreater(spy_send.call_count, 0, "Broker.send_order must have been called by Orchestrator")
            self.assertIsNotNone(exception_caught, "Broker exception must have been raised during execution")
            self.assertIs(exception_caught, broker_exception)

            # 6. [관측 3: Execution/VSSF] ExecutionReport가 생성되지 않았고 executions_handled가 0이며 상태 변동이 전무함 실측
            self.assertEqual(system.executions_handled, 0, "executions_handled must be 0 when broker raises exception")
            self.assertEqual(len(system.vssf.execution_engine.reports), reports_initial)
            self.assertEqual(dict(system.vssf.account.get_positions()), pos_initial)
            self.assertEqual(system.vssf.account.balance, bal_initial)
            self.assertEqual(system.vssf.account.used_margin, margin_initial)
            self.assertEqual(len(system.op_runtime.received_execution_reports), 0)

            await system.shutdown()

        asyncio.run(_run())

    def test_C_separation_of_risk_approval_and_execution_state(self):
        """[TEST C] Broker 실패 후 risk_decision(APPROVE) != broker_result(EXCEPTION) != execution_result(NO_EXECUTION) 상태 분리 및 비혼동 검증."""
        async def _run():
            system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 500_000_000.0})
            await system.initialize()

            # 1. 상태 분리 관측 변수
            observed_risk_decision = None
            observed_broker_result = None
            observed_execution_result = None

            original_admit = system.op_runtime.risk_gate.admit_order

            def spy_admit(*args, **kwargs):
                nonlocal observed_risk_decision
                res = original_admit(*args, **kwargs)
                if res[0] is True and res[1] is not None:
                    observed_risk_decision = "APPROVE"
                else:
                    observed_risk_decision = "DENY"
                return res

            system.op_runtime.risk_gate.admit_order = spy_admit

            # 2. Broker에 RuntimeError Fault Injection
            def faulty_send_order(cmd):
                nonlocal observed_broker_result
                observed_broker_result = "EXCEPTION"
                raise RuntimeError("Broker Rejected by Exchange Line Drop")

            system.broker.send_order = MagicMock(side_effect=faulty_send_order)

            # 3. [단일 실행] Orchestrator 1 틱 실행
            try:
                await system.run_loop(max_ticks=1)
            except RuntimeError:
                pass

            # 4. Execution 결과 관측
            if system.executions_handled == 0 and len(system.op_runtime.received_execution_reports) == 0:
                observed_execution_result = "NO_EXECUTION"
            else:
                observed_execution_result = "FILLED"

            # 5. [핵심 검증 1: 3개 상태의 완벽한 분리]
            self.assertEqual(observed_risk_decision, "APPROVE", "RiskGate decision must be APPROVE")
            self.assertEqual(observed_broker_result, "EXCEPTION", "Broker result must be EXCEPTION")
            self.assertEqual(observed_execution_result, "NO_EXECUTION", "Execution result must be NO_EXECUTION")

            # 6. [핵심 검증 2: APPROVE != FILLED 비혼동 증명]
            # RiskGate가 APPROVE했더라도 execution_result는 FILLED가 아니라 NO_EXECUTION이어야 함
            self.assertNotEqual(observed_execution_result, "FILLED", "APPROVE must NOT be equated with FILLED on broker failure")
            self.assertEqual(len(system.vssf.account.get_positions()), 0, "No positions should exist on broker failure")
            self.assertEqual(system.vssf.account.used_margin, 0.0, "Used margin must remain 0.0 on broker failure")

            await system.shutdown()

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
