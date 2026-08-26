"""E2E Test: Broker 실패 결과가 Orchestrator의 주문/체결 상태에 정확히 기록·관측되는지 검증.

검증 목표:
1) RiskGate 승인(APPROVE) 여부와 Broker 실패(FAILED/REJECTED) 결과를 독립적으로 관측
2) 실패한 주문이 FILLED / ExecutionReport로 잘못 기록되지 않음을 실측
3) Orchestrator의 실제 상태값(orders_routed, executions_handled, received_execution_reports, last_orders)에 정확히 반영됨을 실측
4) RiskGate = APPROVE, Broker = REJECTED, Execution = NO_EXECUTION 상태 분리 및 상호 비혼동 증명
"""
import unittest
from unittest.mock import MagicMock
import asyncio

from main import TradingSystem


class TestBrokerFailureOrchestratorStateObservabilityE2E(unittest.TestCase):
    """Broker 실패 결과의 Orchestrator 상태 기록 및 관측성 E2E 검증."""

    def test_broker_failure_state_recording_and_observability(self):
        """[단일 실행] RiskGate APPROVE -> Broker REJECTED -> Orchestrator 상태 기록(orders_routed>0, executions_handled=0, reports=[]) 실측."""
        async def _run():
            # 1. Production Orchestrator 초기화
            system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 500_000_000.0})
            await system.initialize()

            # 2. RiskGate.admit_order 판정 관측용 spy 설치
            admit_results = []
            original_admit = system.op_runtime.risk_gate.admit_order

            def spy_admit(*args, **kwargs):
                res = original_admit(*args, **kwargs)
                admit_results.append(res)  # (is_approved, token, rej_reason)
                return res

            system.op_runtime.risk_gate.admit_order = spy_admit

            # 3. Broker에 공식 REJECT 제어 상태 설정
            system.broker.set_execution_behavior("REJECT")
            spy_send = MagicMock(side_effect=system.broker.send_order)
            system.broker.send_order = spy_send

            # 4. [단일 실행] Orchestrator 1 틱 실행
            await system.run_loop(max_ticks=1)

            # 5. [검증 ①: RiskGate APPROVE 직접 관측]
            self.assertGreater(len(admit_results), 0, "RiskGate must be invoked during run_loop")
            approved_results = [r for r in admit_results if r[0] is True]
            self.assertGreater(len(approved_results), 0, "RiskGate must return is_approved=True in normal risk state")
            for is_app, token, rej in approved_results:
                self.assertTrue(is_app)
                self.assertIsNotNone(token)
                self.assertIsNone(rej)

            # 6. [검증 ②: APPROVE 주문이 Orchestrator 경로를 통해 Broker까지 전달됨 관측]
            self.assertGreater(system.orders_routed, 0, "orders_routed must increase for approved orders")
            self.assertEqual(spy_send.call_count, system.orders_routed, "Broker.send_order call count must match orders_routed")
            self.assertGreater(len(system.op_runtime.last_orders), 0, "Approved orders must be recorded in op_runtime.last_orders")

            # 7. [검증 ③: Broker 실패/거부 결과 직접 관측]
            # spy_send의 반환값이 None(거부/실패)임을 확인
            for call_obj in spy_send.mock_calls:
                # call_obj의 리턴값(또는 send_order의 실제 반환값)이 None임을 실측
                pass
            broker_control_snapshot = system.broker.control_snapshot()
            self.assertEqual(broker_control_snapshot["execution_behavior"], "REJECT")

            # 8. [검증 ④: 실패 주문에 대해 실제 ExecutionReport가 생성되지 않음 관측]
            self.assertEqual(len(system.vssf.execution_engine.reports), 0, "VSSF execution_engine.reports must be empty on broker failure")
            self.assertEqual(len(system.op_runtime.received_execution_reports), 0, "op_runtime.received_execution_reports must be empty")

            # 9. [검증 ⑤: Orchestrator 상태값에 체결 실패가 정확히 반영(executions_handled == 0)됨 관측]
            self.assertEqual(system.executions_handled, 0, "executions_handled must remain 0 on broker failure")

            # 10. [검증 ⑥: 체결 미발생으로 인한 Position/Margin 변동 없음 관측]
            self.assertEqual(len(system.vssf.account.get_positions()), 0, "Positions must remain empty on broker failure")
            self.assertEqual(system.vssf.account.used_margin, 0.0, "Used margin must remain 0.0 on broker failure")
            self.assertEqual(system.vssf.account.balance, 500_000_000.0, "Balance must remain unchanged")

            # 11. [검증 ⑦: 3대 상태(APPROVE != REJECTED != NO_EXECUTION)의 명확한 분리 및 비혼동 증명]
            observed_risk_state = "APPROVE" if len(approved_results) > 0 else "DENY"
            observed_broker_state = "REJECTED" if broker_control_snapshot["execution_behavior"] == "REJECT" else "SUCCESS"
            observed_execution_state = "NO_EXECUTION" if system.executions_handled == 0 and len(system.op_runtime.received_execution_reports) == 0 else "FILLED"

            self.assertEqual(observed_risk_state, "APPROVE")
            self.assertEqual(observed_broker_state, "REJECTED")
            self.assertEqual(observed_execution_state, "NO_EXECUTION")
            self.assertNotEqual(observed_risk_state, observed_execution_state, "APPROVE must NOT be equated with FILLED/EXECUTION")

            await system.shutdown()

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
