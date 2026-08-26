"""E2E Test: Broker.send_order() 실제 반환값 None <-> Orchestrator 체결 상태 동일 실행 연결 검증.

핵심 연결 관계:
    TradingSystem.run_loop(1)
        ↓
    RiskGate.admit_order() -> APPROVE (is_approved=True, token!=None, rejection_reason=None)
        ↓
    Orchestrator가 Broker.send_order() 호출 (call_count >= 1)
        ↓
    실제 Production Broker (REJECT 모드) 실행 -> 실제 반환값 None 캡처 (return_value is None)
        ↓
    동일 실행 내 ExecutionReport 생성 0건 (vssf.execution_engine.reports == [])
        ↓
    동일 실행 내 executions_handled == 0 & op_runtime.received_execution_reports == []
"""
import unittest
import asyncio

from main import TradingSystem


class TestBrokerSendOrderNoneExecutionStateLinkE2E(unittest.TestCase):
    """단일 run_loop(1) 실행 내 Broker.send_order() 반환값 None과 Orchestrator 체결 0건의 동일 실행 연결 E2E 검증."""

    def test_single_run_loop_broker_none_return_links_to_execution_zero(self):
        """[TEST A] 동일 실행 내 RiskGate APPROVE -> Broker.send_order() 실제 반환값 None -> ExecutionReport 0 & executions_handled 0 연결 실측."""
        async def _run():
            # 1. [1] 실제 TradingSystem 초기화 (5억원 초기 자본금)
            system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 500_000_000.0})
            await system.initialize()

            # 2. Broker를 공식 REJECT 모드로 설정 (실제 Production 제어 메커니즘 사용)
            system.broker.set_execution_behavior("REJECT")

            # 3. RiskGate 판정 실시간 캡처 spy 설치
            admit_results = []
            original_admit = system.op_runtime.risk_gate.admit_order

            def spy_admit(*args, **kwargs):
                res = original_admit(*args, **kwargs)
                admit_results.append(res)  # (is_approved, token, rej_reason)
                return res

            system.op_runtime.risk_gate.admit_order = spy_admit

            # 4. 실제 Broker.send_order() 호출 및 실제 반환값을 있는 그대로 캡처하는 spy 설치
            captured_returns = []
            original_send_order = system.broker.send_order

            def spy_send_order(cmd):
                # 실제 Production Broker.send_order()를 실행하고 그 실제 반환값을 캡처하여 반환
                actual_return = original_send_order(cmd)
                captured_returns.append(actual_return)
                return actual_return

            system.broker.send_order = spy_send_order

            # 5. [1] 단일 run_loop(1) 실행 (Orchestrator 1 틱 실행)
            await system.run_loop(max_ticks=1)

            # 6. [2] 동일 실행에서 RiskGate APPROVE 직접 관측
            self.assertGreater(len(admit_results), 0, "RiskGate.admit_order must be invoked during run_loop")
            approved_results = [r for r in admit_results if r[0] is True]
            self.assertGreater(len(approved_results), 0, "RiskGate must return is_approved=True in normal state")
            for is_app, token, rej in approved_results:
                self.assertTrue(is_app, "is_approved must be True")
                self.assertIsNotNone(token, "token must not be None on APPROVE")
                self.assertIsNone(rej, "rejection_reason must be None on APPROVE")

            # 7. [3] 동일 실행에서 Broker.send_order() 실제 호출 확인
            self.assertGreaterEqual(len(captured_returns), 1, "Broker.send_order() call count must be >= 1")
            self.assertEqual(len(captured_returns), system.orders_routed, "send_order call count must match orders_routed")

            # 8. [4, 5] 실제 send_order() 반환값 직접 캡처 및 None 검증
            for actual_ret in captured_returns:
                self.assertIsNone(actual_ret, "Actual return value of Broker.send_order() must be None on rejection")

            # 9. [6] 동일 실행에서 ExecutionReport == 0 직접 검증
            self.assertEqual(len(system.vssf.execution_engine.reports), 0, "VSSF execution_engine.reports must be exactly 0")
            self.assertEqual(len(system.op_runtime.received_execution_reports), 0, "op_runtime.received_execution_reports must be exactly 0")

            # 10. [7] 동일 실행에서 executions_handled == 0 직접 검증
            self.assertEqual(system.executions_handled, 0, "Orchestrator executions_handled must be exactly 0")

            # 11. [8] 동일 실행 내 핵심 연결성 통합 검증:
            # (RiskGate APPROVE) AND (Broker return None) AND (ExecutionReport == 0) AND (executions_handled == 0)
            self.assertTrue(
                len(approved_results) > 0
                and all(r is None for r in captured_returns)
                and len(system.vssf.execution_engine.reports) == 0
                and system.executions_handled == 0,
                "All 4 conditions must be linked and satisfied within the single execution flow"
            )

            await system.shutdown()

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
