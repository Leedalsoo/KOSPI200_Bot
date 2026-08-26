"""E2E Test: Broker.send_order() 실제 반환값 None <-> Orchestrator 체결 상태(executions_handled=0, reports=0) 동일 실행 연결 검증.

핵심 인과관계:
    Orchestrator 실행 (TradingSystem.run_loop(1))
        ↓
    RiskGate APPROVE (is_approved=True, token!=None)
        ↓
    Broker.send_order() 호출
        ↓
    실제 반환값 == None (직접 캡처)
        ↓
    ExecutionReport 생성 0건 (vssf.execution_engine.reports == [])
        ↓
    executions_handled == 0 & op_runtime.received_execution_reports == []
"""
import unittest
import asyncio

from main import TradingSystem


class TestBrokerNoneReturnToOrchestratorExecutionZeroE2E(unittest.TestCase):
    """Broker.send_order()의 실제 None 반환값과 Orchestrator 체결 0건의 동일 실행 연결 E2E 검증."""

    def test_broker_none_return_causes_orchestrator_execution_zero(self):
        """[단일 실행] RiskGate APPROVE -> Broker.send_order() 반환값 None 직접 캡처 -> executions_handled=0 & reports=0 직접 연결 실측."""
        async def _run():
            # 1. Production Orchestrator 초기화
            system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 500_000_000.0})
            await system.initialize()

            # 2. Broker를 공식 REJECT 모드로 설정하여 send_order()가 None을 반환하도록 유도
            system.broker.set_execution_behavior("REJECT")

            # 3. RiskGate 판정 및 Broker.send_order()의 실제 반환값을 실시간 캡처하는 spy 설치
            admit_results = []
            original_admit = system.op_runtime.risk_gate.admit_order

            def spy_admit(*args, **kwargs):
                res = original_admit(*args, **kwargs)
                admit_results.append(res)  # (is_approved, token, rej_reason)
                return res

            system.op_runtime.risk_gate.admit_order = spy_admit

            captured_send_order_returns = []
            original_send = system.broker.send_order

            def spy_send(*args, **kwargs):
                ret = original_send(*args, **kwargs)
                captured_send_order_returns.append(ret)
                return ret

            system.broker.send_order = spy_send

            # 4. [단일 실행] Orchestrator 1 틱 실행
            await system.run_loop(max_ticks=1)

            # 5. [직접 증거 1: RiskGate APPROVE 판정]
            self.assertGreater(len(admit_results), 0, "RiskGate must be invoked during run_loop")
            approved_results = [r for r in admit_results if r[0] is True]
            self.assertGreater(len(approved_results), 0, "RiskGate must return is_approved=True in normal risk state")

            # 6. [직접 증거 2: Broker.send_order()의 실제 반환값이 None임을 직접 캡처]
            self.assertGreater(len(captured_send_order_returns), 0, "Broker.send_order must have been invoked")
            self.assertEqual(len(captured_send_order_returns), system.orders_routed)
            for ret_val in captured_send_order_returns:
                self.assertIsNone(ret_val, "Broker.send_order() actual return value must be None on rejection")

            # 7. [직접 증거 3: Orchestrator 체결 카운터 executions_handled == 0 직접 연결]
            self.assertEqual(system.executions_handled, 0, "executions_handled must be exactly 0 when broker returns None")

            # 8. [직접 증거 4: VSSF 및 Runtime ExecutionReport 생성 건수 == 0건 직접 연결]
            self.assertEqual(len(system.vssf.execution_engine.reports), 0, "VSSF execution_engine.reports must be 0")
            self.assertEqual(len(system.op_runtime.received_execution_reports), 0, "op_runtime.received_execution_reports must be 0")

            # 9. [직접 증거 5: Position 및 Margin 상태 변동 0건 직접 연결]
            self.assertEqual(len(system.vssf.account.get_positions()), 0)
            self.assertEqual(system.vssf.account.used_margin, 0.0)

            await system.shutdown()

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
