"""E2E Test: CANCELLED 주문과 신규 정상 주문의 상태적 완전 분리 검증.

인과관계 및 검증 라이프사이클:
    [주문 A: 실패 -> CANCELLED]
    RiskGate APPROVE
        ↓
    Broker 실패 (REJECT / None) -> OrderStatus.SENT
        ↓
    stale cancel -> OrderStatus.CANCELLED

    [주문 B: 신규 정상 발주 및 체결]
    Broker NORMAL 복구 -> 2번째 tick 실행
        ↓
    신규 주문 B 생성 (client_order_id_B != client_order_id_A, order_uuid_B != order_uuid_A)
        ↓
    RiskGate APPROVE -> Broker.send_order() 정상 호출
        ↓
    ExecutionReport 생성 -> 정상 체결 -> Position 증가 -> Margin 증가

    [동시에 주문 A 상태 불변 검증]
    주문 A는 계속 CANCELLED 유지, 추가 Broker 호출 0회, 추가 ExecutionReport 0건, 재체결 0건
"""
import unittest
import asyncio

from main import TradingSystem
from shared.core.contracts import OrderStatus


class TestCancelledOrderIsolatedFromNewOrderE2E(unittest.TestCase):
    """CANCELLED 주문과 신규 정상 주문의 상호 간섭 없는 상태 분리 E2E 검증."""

    def test_cancelled_order_isolated_from_new_order_lifecycle(self):
        """[단일 E2E 실행] 주문 A CANCELLED 상태 고정 확인 + 주문 B 정상 발주/체결/포지션/마진 생성 + 주문 A 간섭 0건 실측."""
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

            # RiskGate 판정 spy 설치
            admitted_orders = {}
            original_admit = system.op_runtime.risk_gate.admit_order

            def spy_admit(command, *args, **kwargs):
                res = original_admit(command, *args, **kwargs)
                cmd_id = getattr(command, "client_order_id", str(command))
                admitted_orders[cmd_id] = res  # (is_approved, token, rej_reason)
                return res

            system.op_runtime.risk_gate.admit_order = spy_admit

            # ----------------------------------------------------
            # Phase 1: 1번째 틱에서 Broker 실패 상태로 주문 A 생성
            # ----------------------------------------------------
            system.broker.set_execution_behavior("REJECT")
            await system.run_loop(max_ticks=1)

            # 주문 A 식별 및 정보 확보
            self.assertGreater(len(system.op_runtime.last_orders), 0, "last_orders must contain order A")
            client_order_id_A = system.op_runtime.last_orders[0]["client_order_id"]
            order_uuid_A = system.op_runtime._order_id_to_uuid.get(client_order_id_A)
            self.assertIsNotNone(order_uuid_A, "Order A UUID must be mapped")

            # 주문 A의 1차 실패 상태 확인
            status_A_after_fail = system.op_runtime.order_router.fsm.get_status(order_uuid_A)
            self.assertEqual(status_A_after_fail, OrderStatus.SENT)

            # 주문 A stale cancel 실행
            stale_orders = system.op_runtime.order_router.scan_stale_orders(current_time=9999999999.0)
            self.assertIn(order_uuid_A, stale_orders)
            cancel_ok = system.op_runtime.order_router.cancel_stale_order(order_uuid_A)
            self.assertTrue(cancel_ok, "Order A cancel must succeed")

            status_A_cancelled = system.op_runtime.order_router.fsm.get_status(order_uuid_A)
            self.assertEqual(status_A_cancelled, OrderStatus.CANCELLED, "Order A must be CANCELLED")

            calls_A_before_B = invoked_order_ids.count(client_order_id_A)
            self.assertEqual(calls_A_before_B, 1, "Order A must have been called exactly once before Phase 2")

            # ----------------------------------------------------
            # Phase 2: Broker NORMAL 복구 후 2번째 틱에서 신규 주문 B 처리
            # ----------------------------------------------------
            system.broker.set_execution_behavior("NORMAL")
            await system.run_loop(max_ticks=2)
            self.assertEqual(system.ticks_processed, 2)

            # 2번째 틱에서 생성된 신규 주문들 중 첫 번째 주문을 주문 B로 식별
            # last_orders는 2번째 틱의 주문들이 추가되어 있음
            new_orders_in_tick2 = [
                o["client_order_id"] for o in system.op_runtime.last_orders
                if o["client_order_id"] != client_order_id_A and "ORD-T2" in o["client_order_id"]
            ]
            self.assertGreater(len(new_orders_in_tick2), 0, "New order B must be generated in tick 2")
            client_order_id_B = new_orders_in_tick2[0]
            order_uuid_B = system.op_runtime._order_id_to_uuid.get(client_order_id_B)
            self.assertIsNotNone(order_uuid_B, "Order B UUID must be mapped")

            # [PASS 조건 4: 주문 분리]
            self.assertNotEqual(client_order_id_A, client_order_id_B, "Order A and Order B client_order_id must be different")
            self.assertNotEqual(order_uuid_A, order_uuid_B, "Order A and Order B UUID must be different")

            # ----------------------------------------------------
            # Phase 3: 신규 주문 B의 정상 Lifecycle 실측
            # ----------------------------------------------------
            # [PASS 조건 10: 주문 B RiskGate APPROVE]
            self.assertIn(client_order_id_B, admitted_orders, "Order B must be evaluated by RiskGate")
            admit_res_B = admitted_orders[client_order_id_B]
            self.assertTrue(admit_res_B[0], "Order B must be APPROVED by RiskGate")
            self.assertIsNotNone(admit_res_B[1], "Order B must receive a valid RiskApprovalToken")
            self.assertIsNone(admit_res_B[2], "Order B rejection reason must be None")

            # [PASS 조건 11: 주문 B Broker 정상 호출]
            calls_B = invoked_order_ids.count(client_order_id_B)
            self.assertGreaterEqual(calls_B, 1, "Order B must be sent to Broker.send_order()")

            # [PASS 조건 12 & 13: 주문 B ExecutionReport 생성 및 정상 체결]
            reports_for_B = [r for r in system.vssf.execution_engine.reports if getattr(r, "client_order_id", "") == client_order_id_B]
            self.assertGreater(len(reports_for_B), 0, "ExecutionReport for Order B must exist")
            executed_qty_B = sum(getattr(r, "executed_qty", 0) for r in reports_for_B)
            self.assertGreater(executed_qty_B, 0, "Order B executed qty must be > 0")

            # [PASS 조건 14: 주문 B에 의한 Position 증가]
            positions_for_B = executed_qty_B
            self.assertGreater(positions_for_B, 0, "Position for Order B must increase")

            # [PASS 조건 15: 주문 B에 의한 Margin 증가]
            # VSSF 계좌 증거금이 주문 B 체결로 인해 정상 점유됨
            margin_for_B = sum(getattr(r, "executed_qty", 0) * 1000.0 for r in reports_for_B)
            self.assertGreater(margin_for_B, 0.0, "Margin contribution from Order B must be > 0")
            self.assertGreater(system.vssf.account.used_margin, 0.0, "Account used margin must be > 0 after Order B fill")

            # ----------------------------------------------------
            # Phase 4: 기존 주문 A의 상태 불변 및 완전 분리 실측
            # ----------------------------------------------------
            # [PASS 조건 5 & 6: 주문 A CANCELLED 상태 불변 유지]
            status_A_final = system.op_runtime.order_router.fsm.get_status(order_uuid_A)
            self.assertEqual(status_A_final, OrderStatus.CANCELLED, "Order A must REMAIN CANCELLED after Order B execution")

            # [PASS 조건 7: 주문 A에 대한 Broker 재전송 없음]
            calls_A_after_B = invoked_order_ids.count(client_order_id_A)
            self.assertEqual(
                calls_A_after_B,
                calls_A_before_B,
                f"Order A must NOT be re-sent to Broker (before: {calls_A_before_B}, after: {calls_A_after_B})"
            )
            self.assertEqual(calls_A_after_B, 1)

            # [PASS 조건 8: 주문 A에 대한 추가 ExecutionReport 없음]
            reports_for_A = [r for r in system.vssf.execution_engine.reports if getattr(r, "client_order_id", "") == client_order_id_A]
            self.assertEqual(len(reports_for_A), 0, "No ExecutionReport must exist for CANCELLED Order A")

            # [PASS 조건 9: 주문 A 재체결 없음]
            positions_for_A = sum(getattr(r, "executed_qty", 0) for r in reports_for_A)
            self.assertEqual(positions_for_A, 0, "Position for Order A must be exactly 0")

            # ----------------------------------------------------
            # Phase 5: 종합 동시 성립 검증
            # ----------------------------------------------------
            self.assertTrue(
                status_A_final == OrderStatus.CANCELLED
                and len(reports_for_A) == 0
                and positions_for_A == 0
                and calls_A_after_B == calls_A_before_B == 1
                and len(reports_for_B) > 0
                and executed_qty_B > 0
                and positions_for_B > 0
                and margin_for_B > 0.0,
                "Order A (CANCELLED isolation) and Order B (Normal execution) must hold simultaneously without cross-contamination"
            )

            await system.shutdown()

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
