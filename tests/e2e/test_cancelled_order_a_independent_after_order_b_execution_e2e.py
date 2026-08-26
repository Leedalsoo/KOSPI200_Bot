"""E2E Test: CANCELLED 주문 A의 신규 주문 B 체결 이후 완전한 독립성 검증.

인과관계 및 검증 라이프사이클:
    [주문 A: 실패 -> CANCELLED]
    RiskGate APPROVE -> Broker 실패 (REJECT / None) -> OrderStatus.SENT
        ↓
    stale cancel 실행 -> OrderStatus.CANCELLED
        ↓
    CANCELLED 직후 주문 A 귀속 기준값 저장:
    - positions_A_before
    - used_margin_A_before
    - executions_A_before

    [주문 B: 정상 발주 및 체결]
    Broker NORMAL 복구 -> 2번째 tick 실행
        ↓
    신규 주문 B 생성 (client_order_id_B != client_order_id_A, order_uuid_B != order_uuid_A)
        ↓
    RiskGate APPROVE -> Broker.send_order() 정상 호출
        ↓
    ExecutionReport 생성 -> 주문 B 정상 체결 (executed_qty > 0)
        ↓
    주문 B에 의한 계좌 전체 Position/Margin 증가 관측

    [주문 A의 독립성 실측]
    주문 B 체결 이후 주문 A 귀속 측정값 저장:
    - positions_A_after
    - used_margin_A_after
    - executions_A_after
        ↓
    명시적 equality assertion 검증:
    assert positions_A_after == positions_A_before
    assert used_margin_A_after == used_margin_A_before
    assert executions_A_after == executions_A_before
    assert status_A == OrderStatus.CANCELLED
    assert calls_A_after == calls_A_before (재전송 없음)
"""
import unittest
import asyncio

from main import TradingSystem
from shared.core.contracts import OrderStatus


class TestCancelledOrderAIndependentAfterOrderBExecutionE2E(unittest.TestCase):
    """주문 B 정상 체결 이후에도 주문 A의 상태/체결/포지션/마진이 독립적으로 보존되는지 E2E 검증."""

    def test_cancelled_order_a_independent_after_order_b_execution(self):
        """[단일 E2E 실행] 주문 A CANCELLED 기준값 저장 -> 주문 B 정상 체결 -> 주문 A 귀속 상태 불변 및 독립성 실측."""
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
                admitted_orders[cmd_id] = res
                return res

            system.op_runtime.risk_gate.admit_order = spy_admit

            # ----------------------------------------------------
            # Phase 1: 1번째 틱에서 Broker 실패 상태로 주문 A 생성 및 CANCELLED 처리
            # ----------------------------------------------------
            system.broker.set_execution_behavior("REJECT")
            await system.run_loop(max_ticks=1)

            # 주문 A 식별 및 정보 확보
            self.assertGreater(len(system.op_runtime.last_orders), 0, "last_orders must contain order A")
            client_order_id_A = system.op_runtime.last_orders[0]["client_order_id"]
            order_uuid_A = system.op_runtime._order_id_to_uuid.get(client_order_id_A)
            self.assertIsNotNone(order_uuid_A, "Order A UUID must be mapped")

            # 주문 A stale cancel 실행
            stale_orders = system.op_runtime.order_router.scan_stale_orders(current_time=9999999999.0)
            self.assertIn(order_uuid_A, stale_orders)
            cancel_ok = system.op_runtime.order_router.cancel_stale_order(order_uuid_A)
            self.assertTrue(cancel_ok, "Order A cancel must succeed")

            # [주문 A CANCELLED 확인]
            status_A_cancelled = system.op_runtime.order_router.fsm.get_status(order_uuid_A)
            self.assertEqual(status_A_cancelled, OrderStatus.CANCELLED, "Order A must be CANCELLED")

            # [주문 A CANCELLED 직후 귀속 기준값 직접 저장 (before 측정값)]
            reports_A_before = [r for r in system.vssf.execution_engine.reports if getattr(r, "client_order_id", "") == client_order_id_A]
            positions_A_before = sum(getattr(r, "executed_qty", 0) for r in reports_A_before)
            used_margin_A_before = 0.0 if len(reports_A_before) == 0 else sum(getattr(r, "executed_qty", 0) * 1000.0 for r in reports_A_before)
            executions_A_before = len(reports_A_before)

            self.assertEqual(positions_A_before, 0)
            self.assertEqual(used_margin_A_before, 0.0)
            self.assertEqual(executions_A_before, 0)

            calls_A_before = invoked_order_ids.count(client_order_id_A)
            self.assertEqual(calls_A_before, 1, "Order A must be called once in tick 1")

            # ----------------------------------------------------
            # Phase 2: Broker NORMAL 복구 후 2번째 틱에서 신규 주문 B 처리
            # ----------------------------------------------------
            system.broker.set_execution_behavior("NORMAL")
            await system.run_loop(max_ticks=2)
            self.assertEqual(system.ticks_processed, 2)

            # 주문 B 식별
            new_orders_in_tick2 = [
                o["client_order_id"] for o in system.op_runtime.last_orders
                if o["client_order_id"] != client_order_id_A and "ORD-T2" in o["client_order_id"]
            ]
            self.assertGreater(len(new_orders_in_tick2), 0, "New order B must be generated in tick 2")
            client_order_id_B = new_orders_in_tick2[0]
            order_uuid_B = system.op_runtime._order_id_to_uuid.get(client_order_id_B)
            self.assertIsNotNone(order_uuid_B, "Order B UUID must be mapped")

            # [A/B ID 분리 확인]
            self.assertNotEqual(client_order_id_A, client_order_id_B, "Order A and B client_order_id must differ")
            self.assertNotEqual(order_uuid_A, order_uuid_B, "Order A and B UUID must differ")

            # [주문 B 정상 Lifecycle 실측]
            # 1) RiskGate APPROVE
            self.assertIn(client_order_id_B, admitted_orders)
            admit_res_B = admitted_orders[client_order_id_B]
            self.assertTrue(admit_res_B[0], "Order B must be APPROVED by RiskGate")
            self.assertIsNotNone(admit_res_B[1], "Order B must have token")

            # 2) Broker 정상 호출
            calls_B = invoked_order_ids.count(client_order_id_B)
            self.assertGreaterEqual(calls_B, 1, "Order B must be sent to Broker")

            # 3) ExecutionReport 생성 및 체결
            reports_B = [r for r in system.vssf.execution_engine.reports if getattr(r, "client_order_id", "") == client_order_id_B]
            self.assertGreater(len(reports_B), 0, "ExecutionReport for Order B must exist")
            executed_qty_B = sum(getattr(r, "executed_qty", 0) for r in reports_B)
            self.assertGreater(executed_qty_B, 0, "Order B executed qty must be > 0")

            # 4) Position / Margin 증가
            positions_B = executed_qty_B
            margin_B = sum(getattr(r, "executed_qty", 0) * 1000.0 for r in reports_B)
            self.assertGreater(positions_B, 0, "Order B Position must increase")
            self.assertGreater(margin_B, 0.0, "Order B Margin must increase")
            self.assertGreater(system.vssf.account.used_margin, 0.0, "Total account used margin must increase after Order B")

            # ----------------------------------------------------
            # Phase 3: 주문 B 체결 이후 주문 A 귀속 상태 측정 및 명시적 equality assertion
            # ----------------------------------------------------
            reports_A_after = [r for r in system.vssf.execution_engine.reports if getattr(r, "client_order_id", "") == client_order_id_A]
            positions_A_after = sum(getattr(r, "executed_qty", 0) for r in reports_A_after)
            used_margin_A_after = 0.0 if len(reports_A_after) == 0 else sum(getattr(r, "executed_qty", 0) * 1000.0 for r in reports_A_after)
            executions_A_after = len(reports_A_after)

            # [명시적 equality assertion 1: Position]
            self.assertEqual(
                positions_A_after,
                positions_A_before,
                f"Order A Position must remain equal before and after Order B (before: {positions_A_before}, after: {positions_A_after})"
            )
            self.assertEqual(positions_A_after, 0)

            # [명시적 equality assertion 2: Margin]
            self.assertEqual(
                used_margin_A_after,
                used_margin_A_before,
                f"Order A Margin must remain equal before and after Order B (before: {used_margin_A_before}, after: {used_margin_A_after})"
            )
            self.assertEqual(used_margin_A_after, 0.0)

            # [명시적 equality assertion 3: ExecutionReport / Executions]
            self.assertEqual(
                executions_A_after,
                executions_A_before,
                f"Order A Executions must remain equal before and after Order B (before: {executions_A_before}, after: {executions_A_after})"
            )
            self.assertEqual(executions_A_after, 0)

            # [추가 검증: CANCELLED 상태 유지 및 재전송 없음]
            status_A_after_B = system.op_runtime.order_router.fsm.get_status(order_uuid_A)
            self.assertEqual(status_A_after_B, OrderStatus.CANCELLED, "Order A must REMAIN CANCELLED")

            calls_A_after = invoked_order_ids.count(client_order_id_A)
            self.assertEqual(
                calls_A_after,
                calls_A_before,
                f"Order A Broker calls must not increase (before: {calls_A_before}, after: {calls_A_after})"
            )
            self.assertEqual(calls_A_after, 1)

            # [종합 독립성 성립 assertion]
            self.assertTrue(
                positions_A_after == positions_A_before == 0
                and used_margin_A_after == used_margin_A_before == 0.0
                and executions_A_after == executions_A_before == 0
                and status_A_after_B == OrderStatus.CANCELLED
                and calls_A_after == calls_A_before == 1
                and positions_B > 0
                and margin_B > 0.0,
                "Order A must remain 100% independent and unaffected after Order B execution"
            )

            await system.shutdown()

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
