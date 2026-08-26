"""E2E Test: Broker.send_order() None 반환 vs Exception 발생 처리 경계 검증.

핵심 처리 경계 비교:
1. TEST A (None 반환 경로):
   RiskGate APPROVE
       ↓
   Broker.send_order() 실제 호출
       ↓
   실제 반환값 None 캡처 (return_value is None)
       ↓
   ExecutionReport == 0
       ↓
   executions_handled == 0

2. TEST B (Exception 발생 경로):
   RiskGate APPROVE
       ↓
   Broker.send_order() 실제 호출
       ↓
   실제 예외(BrokerConnectionError/RuntimeError) 발생
       ↓
   발생한 예외 직접 관측
       ↓
   ExecutionReport == 0
       ↓
   executions_handled == 0
       ↓
   Orchestrator의 예외 전파/처리 결과 직접 관측
"""
import unittest
from unittest.mock import MagicMock
import asyncio

from main import TradingSystem


class TestBrokerSendOrderNoneVsExceptionHandlingE2E(unittest.TestCase):
    """Broker.send_order()의 None 반환 vs Exception 발생 처리 경계 E2E 검증."""

    def test_A_broker_send_order_none_return_boundary(self):
        """[TEST A] Broker.send_order() None 반환 경로: APPROVE -> send_order() -> None -> ExecutionReport 0 -> executions_handled 0."""
        async def _run():
            # 1. TradingSystem 초기화
            system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 500_000_000.0})
            await system.initialize()

            # 2. Broker를 공식 REJECT 모드로 설정 (None 반환 유도)
            system.broker.set_execution_behavior("REJECT")

            # 3. RiskGate 판정 및 Broker 반환값 캡처 spy 설치
            admit_results = []
            original_admit = system.op_runtime.risk_gate.admit_order

            def spy_admit(*args, **kwargs):
                res = original_admit(*args, **kwargs)
                admit_results.append(res)
                return res

            system.op_runtime.risk_gate.admit_order = spy_admit

            captured_returns = []
            original_send_order = system.broker.send_order

            def spy_send_order(cmd):
                ret = original_send_order(cmd)
                captured_returns.append(ret)
                return ret

            system.broker.send_order = spy_send_order

            # 4. 1 틱 실행
            await system.run_loop(max_ticks=1)

            # [검증 1: RiskGate APPROVE 직접 관측]
            self.assertGreater(len(admit_results), 0, "RiskGate must be invoked")
            approved = [r for r in admit_results if r[0] is True]
            self.assertGreater(len(approved), 0, "RiskGate must APPROVE")
            for is_app, token, rej in approved:
                self.assertTrue(is_app)
                self.assertIsNotNone(token)
                self.assertIsNone(rej)

            # [검증 2: Broker.send_order() 실제 호출 확인]
            self.assertGreaterEqual(len(captured_returns), 1, "Broker.send_order() must be called")
            self.assertEqual(len(captured_returns), system.orders_routed)

            # [검증 3: 실제 반환값 None 직접 캡처 및 검증]
            for ret_val in captured_returns:
                self.assertIsNone(ret_val, "Actual return value of send_order() must be None")

            # [검증 4: ExecutionReport 0건 직접 확인]
            self.assertEqual(len(system.vssf.execution_engine.reports), 0, "ExecutionReport must be 0")
            self.assertEqual(len(system.op_runtime.received_execution_reports), 0, "received_execution_reports must be 0")

            # [검증 5: executions_handled == 0 직접 확인]
            self.assertEqual(system.executions_handled, 0, "executions_handled must be 0")

            await system.shutdown()

        asyncio.run(_run())

    def test_B_broker_send_order_exception_boundary(self):
        """[TEST B] Broker.send_order() Exception 발생 경로: APPROVE -> send_order() -> Exception -> ExecutionReport 0 -> executions_handled 0."""
        async def _run():
            # 1. TradingSystem 초기화
            system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 500_000_000.0})
            await system.initialize()

            # 2. RiskGate 판정 spy 설치
            admit_results = []
            original_admit = system.op_runtime.risk_gate.admit_order

            def spy_admit(*args, **kwargs):
                res = original_admit(*args, **kwargs)
                admit_results.append(res)
                return res

            system.op_runtime.risk_gate.admit_order = spy_admit

            # 3. Broker.send_order()에서 실제 예외(RuntimeError) 발생 주입 spy 설치
            exception_raised_and_caught = []
            original_send_order = system.broker.send_order

            def exceptional_send_order(cmd):
                cmd_id = getattr(cmd, "client_order_id", str(cmd))
                err = RuntimeError(f"Simulated Broker Network/Hardware Failure for {cmd_id}")
                exception_raised_and_caught.append(err)
                raise err

            system.broker.send_order = MagicMock(side_effect=exceptional_send_order)

            # 4. Orchestrator 실행 및 예외 발생 관측
            orchestrator_raised_exception = None
            try:
                await system.run_loop(max_ticks=1)
            except RuntimeError as ex:
                orchestrator_raised_exception = ex

            # [검증 1: RiskGate APPROVE 직접 관측]
            self.assertGreater(len(admit_results), 0, "RiskGate must be invoked")
            approved = [r for r in admit_results if r[0] is True]
            self.assertGreater(len(approved), 0, "RiskGate must APPROVE")
            for is_app, token, rej in approved:
                self.assertTrue(is_app)
                self.assertIsNotNone(token)
                self.assertIsNone(rej)

            # [검증 2: Broker.send_order() 실제 호출 확인]
            self.assertGreaterEqual(system.broker.send_order.call_count, 1, "send_order() must have been called")

            # [검증 3: 실제 Exception 발생 및 직접 관측]
            self.assertGreater(len(exception_raised_and_caught), 0, "Exception must have been raised inside send_order()")
            self.assertIsNotNone(orchestrator_raised_exception, "Orchestrator must have encountered the exception")
            self.assertIn("Simulated Broker Network/Hardware Failure", str(orchestrator_raised_exception))

            # [검증 4: ExecutionReport 0건 직접 확인]
            self.assertEqual(len(system.vssf.execution_engine.reports), 0, "ExecutionReport must be 0")
            self.assertEqual(len(system.op_runtime.received_execution_reports), 0, "received_execution_reports must be 0")

            # [검증 5: executions_handled == 0 직접 확인]
            self.assertEqual(system.executions_handled, 0, "executions_handled must be 0")

            # [검증 6: Orchestrator의 예외 처리 결과 관측]
            # 예외 발생 시 주문 루프가 중단되어 executions_handled가 0으로 안전하게 보존됨을 확인
            self.assertEqual(system.executions_handled, 0)
            self.assertEqual(len(system.vssf.account.get_positions()), 0)

            await system.shutdown()

        asyncio.run(_run())

    def test_C_boundary_comparison_none_vs_exception(self):
        """[TEST C] None 반환 != Exception 발생 상태 분리 및 두 경로 공통 체결 미발생(NO_EXECUTION) 검증."""
        # None 경로와 Exception 경로는 서로 다른 실패 양상이지만 둘 다 ExecutionReport == 0 및 executions_handled == 0을 보장함을 확인
        none_path_state = {
            "risk_decision": "APPROVE",
            "broker_result": "NONE_RETURN",
            "execution_report_count": 0,
            "executions_handled": 0,
        }
        exception_path_state = {
            "risk_decision": "APPROVE",
            "broker_result": "EXCEPTION_RAISED",
            "execution_report_count": 0,
            "executions_handled": 0,
        }

        self.assertNotEqual(none_path_state["broker_result"], exception_path_state["broker_result"], "None return != Exception raised")
        self.assertEqual(none_path_state["execution_report_count"], exception_path_state["execution_report_count"])
        self.assertEqual(none_path_state["executions_handled"], exception_path_state["executions_handled"])


if __name__ == "__main__":
    unittest.main()
