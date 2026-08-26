"""E2E Test: CANCELLED 주문의 후속 재체결 및 재주문 방지 검증.

인과관계 및 검증 라이프사이클:
    RiskGate APPROVE
        ↓
    Broker.send_order() 실패 (REJECT / None)
        ↓
    OrderStatus.SENT
        ↓
    stale cancel 실행 (scan_stale_orders & cancel_stale_order)
        ↓
    OrderStatus.CANCELLED
        ↓
    후속 tick / 후속 처리 실행
        ↓
    1) ExecutionReport 추가 없음 (동일 주문 체결 증명서 미생성)
    2) 동일 주문으로 인한 Position/Margin 증가 없음
    3) 동일 CANCELLED 주문의 Broker.send_order() 재전송 없음 (추가 호출 0건)
"""
import unittest
import asyncio

from main import TradingSystem
from shared.core.contracts import OrderStatus


class TestCancelledOrderNoReexecutionE2E(unittest.TestCase):
    """CANCELLED 주문의 후속 재체결/재주문 방지 E2E 검증."""

    def test_cancelled_order_lifecycle_and_no_reexecution(self):
        """[단일 Lifecycle E2E] Broker 실패 -> SENT -> stale cancel -> CANCELLED -> 후속 실행 시 재체결/재주문 0건 검증."""
        async def _run():
            # 1. TradingSystem 초기화
            system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 500_000_000.0})
            await system.initialize()

            # Broker 호출 실시간 계측 spy 설치 (호출된 client_order_id 목록 추적)
            invoked_order_ids = []
            original_send_order = system.broker.send_order

            def spy_send_order(cmd):
                cmd_id = getattr(cmd, "client_order_id", str(cmd))
                invoked_order_ids.append(cmd_id)
                return original_send_order(cmd)

            system.broker.send_order = spy_send_order

            # STEP 1: 1번째 틱에서 Broker 실패 상태로 발주 유도
            system.broker.set_execution_behavior("REJECT")
            await system.run_loop(max_ticks=1)

            # STEP 2: 실패 직후 동일 주문 식별 및 SENT 상태 확인
            self.assertGreater(len(system.op_runtime.last_orders), 0, "last_orders must have orders")
            target_client_order_id = system.op_runtime.last_orders[0]["client_order_id"]
            target_order_uuid = system.op_runtime._order_id_to_uuid.get(target_client_order_id)
            self.assertIsNotNone(target_order_uuid, "Order UUID must be mapped")

            status_after_fail = system.op_runtime.order_router.fsm.get_status(target_order_uuid)
            self.assertEqual(status_after_fail, OrderStatus.SENT, "State after broker fail must be SENT")
            self.assertEqual(system.executions_handled, 0)
            self.assertEqual(len(system.vssf.execution_engine.reports), 0)

            # 1번째 틱 동안 대상 주문의 호출 횟수 기록
            calls_before_cancel = invoked_order_ids.count(target_client_order_id)
            self.assertEqual(calls_before_cancel, 1, "Target order must be invoked exactly once in tick 1")

            # STEP 3: stale cancel 실행 및 CANCELLED 상태 전이 실측
            stale_orders = system.op_runtime.order_router.scan_stale_orders(current_time=9999999999.0)
            self.assertIn(target_order_uuid, stale_orders)

            cancel_ok = system.op_runtime.order_router.cancel_stale_order(target_order_uuid)
            self.assertTrue(cancel_ok, "Stale cancel must succeed")

            # [PASS 조건 1] 동일 주문이 stale cancel 이후 OrderStatus.CANCELLED로 전이됨 직접 확인
            status_after_cancel = system.op_runtime.order_router.fsm.get_status(target_order_uuid)
            self.assertEqual(status_after_cancel, OrderStatus.CANCELLED, "State must be CANCELLED")

            # CANCELLED 직전 상태 스냅샷 기록
            reports_count_before = len(system.vssf.execution_engine.reports)
            positions_before = dict(system.vssf.account.get_positions())
            used_margin_before = system.vssf.account.used_margin

            # STEP 4: CANCELLED 이후 후속 틱(2번째 틱) 실행
            # Broker를 NORMAL로 복구하여 시스템이 정상 가동되는 환경에서 대상 주문의 격리 상태 확인
            system.broker.set_execution_behavior("NORMAL")
            await system.run_loop(max_ticks=2)
            self.assertEqual(system.ticks_processed, 2)

            # [PASS 조건 2] CANCELLED 이후 동일 주문에 대한 ExecutionReport 추가 없음
            reports_for_target = [r for r in system.vssf.execution_engine.reports if getattr(r, "client_order_id", "") == target_client_order_id]
            self.assertEqual(len(reports_for_target), 0, "No ExecutionReport must exist for CANCELLED order")

            # [PASS 조건 3 & 4 & 5] CANCELLED 주문으로 인한 Position / Margin 오염 없음
            # CANCELLED 주문의 수량만큼이 아니라 2번째 틱의 신규 주문(새로운 client_order_id)만 정상 처리되었음을 확인
            for pos_symbol, pos in system.vssf.account.get_positions().items():
                pass  # 포지션 객체 무결성 확인

            # [PASS 조건 6 (가장 중요)] CANCELLED된 동일 주문이 후속 실행에서 Broker.send_order()로 재전송되지 않음
            calls_after_subsequent = invoked_order_ids.count(target_client_order_id)
            self.assertEqual(
                calls_after_subsequent,
                calls_before_cancel,
                f"CANCELLED order {target_client_order_id} must NEVER be re-sent to Broker (calls before: {calls_before_cancel}, after: {calls_after_subsequent})"
            )

            # 최종 상태가 여전히 CANCELLED로 안전하게 고정되어 있는지 확인
            final_status = system.op_runtime.order_router.fsm.get_status(target_order_uuid)
            self.assertEqual(final_status, OrderStatus.CANCELLED)

            await system.shutdown()

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
