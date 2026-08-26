"""E2E Test: Broker 실패 주문의 최종 주문 상태(Order Final State) 및 주문 ID 추적성 검증.

인과관계 및 검증 범위:
    RiskGate APPROVE
        ↓
    Broker.send_order() 호출
        ↓
    Broker 실패 (REJECT / None 반환 또는 Exception)
        ↓
    ExecutionReport 없음 (len(reports) == 0)
        ↓
    동일 주문 ID(client_order_id -> order_uuid) 기준 최종 주문 상태 직접 조회
        ↓
    Production OrderStatus 정의 상태값(SENT / REJECTED / CANCELLED) 실측 및 종료 상태 여부 판정
"""
import unittest
import asyncio

from main import TradingSystem
from shared.core.contracts import OrderStatus


class TestBrokerFailureOrderFinalStateE2E(unittest.TestCase):
    """Broker 실패 후 동일 주문 ID 기준 최종 주문 상태 실측 E2E 검증."""

    def test_broker_failure_order_state_tracking_and_final_state(self):
        """[TEST A & B] 단일 run_loop(1) 실행 내 주문 ID 추적 및 Broker 실패 후 주문 상태 실측."""
        async def _run():
            # 1. TradingSystem 초기화
            system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 500_000_000.0})
            await system.initialize()

            # 2. Broker를 공식 REJECT 모드로 설정
            system.broker.set_execution_behavior("REJECT")

            # 3. RiskGate 판정 spy 설치
            admit_results = []
            original_admit = system.op_runtime.risk_gate.admit_order

            def spy_admit(*args, **kwargs):
                res = original_admit(*args, **kwargs)
                admit_results.append(res)
                return res

            system.op_runtime.risk_gate.admit_order = spy_admit

            # 4. [단일 실행] Orchestrator 1 틱 실행
            await system.run_loop(max_ticks=1)

            # 5. [검증 1: RiskGate APPROVE 직접 관측]
            self.assertGreater(len(admit_results), 0, "RiskGate must be invoked")
            approved = [r for r in admit_results if r[0] is True]
            self.assertGreater(len(approved), 0, "RiskGate must APPROVE")

            # 6. [검증 2: 주문 ID 식별 및 추적성 확인]
            self.assertGreater(len(system.op_runtime.last_orders), 0, "last_orders must contain approved orders")
            first_order_info = system.op_runtime.last_orders[0]
            target_client_order_id = first_order_info["client_order_id"]
            self.assertIsNotNone(target_client_order_id)

            # _order_id_to_uuid를 통해 주문 UUID 조회
            target_order_uuid = system.op_runtime._order_id_to_uuid.get(target_client_order_id)
            self.assertIsNotNone(target_order_uuid, "Order UUID must be mapped and retrievable for target client_order_id")

            # 7. [검증 3: ExecutionReport 미생성 및 체결 0건 확인]
            self.assertEqual(len(system.vssf.execution_engine.reports), 0, "ExecutionReport must be 0")
            self.assertEqual(system.executions_handled, 0, "executions_handled must be 0")

            # 8. [검증 4: 동일 주문 ID 기준 최종 주문 상태 직접 조회]
            final_order_status = system.op_runtime.order_router.fsm.get_status(target_order_uuid)
            self.assertIsNotNone(final_order_status, "Order status in OMS FSM must not be None")
            self.assertIsInstance(final_order_status, OrderStatus, "Status must be an instance of Production OrderStatus enum")

            # [실측 기록] 현재 Production Orchestrator 파이프라인에서 Broker 실패 시의 실제 상태값
            # run_loop 내에서 Broker.send_order()가 None을 반환했을 때, FSM 상태는 SENT로 유지됨
            self.assertEqual(final_order_status, OrderStatus.SENT)

            # 9. [검증 5: Stale Order Cancel 메커니즘을 통한 최종 CANCELLED 종료 상태 전이 실측]
            # 30초 타임아웃 경과 시뮬레이션
            stale_orders = system.op_runtime.order_router.scan_stale_orders(current_time=9999999999.0)
            self.assertIn(target_order_uuid, stale_orders, "Target order must be detected as stale after timeout")

            cancelled_success = system.op_runtime.order_router.cancel_stale_order(target_order_uuid)
            self.assertTrue(cancelled_success, "Stale order cancel must succeed")

            # 취소 후 최종 종료 상태 확인
            terminal_status = system.op_runtime.order_router.fsm.get_status(target_order_uuid)
            self.assertEqual(terminal_status, OrderStatus.CANCELLED, "After cancel, order state must be OrderStatus.CANCELLED")

            await system.shutdown()

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
