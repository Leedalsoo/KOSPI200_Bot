"""E2E Test: RiskGate 판정 결과의 실제 관측/추적성 + 주문 거부 사유와 Orchestrator 행동의 1:1 연결 검증.

핵심 검증 대상:
- Risk 상태 (Account / Margin / PnL / Market Data)
    ↓
- RiskGate 판정 (APPROVE vs DENY)
    ↓
- 판정 결과 및 실제 거부 사유(rejection reason/code)의 실시간 관측 및 추적성
    ↓
- Orchestrator (TradingSystem.run_loop()) 행동의 1:1 대응
    ├─ APPROVE -> orders_routed > 0 -> Broker 자동 실행 -> Execution/Position mutation
    └─ DENY -> orders_routed = 0 -> Broker 미호출 -> VSSF mutation = 0

4대 시나리오:
- TEST A: APPROVE 판정의 실제 관측 + Orchestrator 자동 실행 실측
- TEST B: DENY 판정 + 실제 거부 사유 관측 + 1:1 차단 행동 연결 실측
- TEST C: 서로 다른 DENY 사유(EXCEEDED_MAX_DAILY_LOSS vs EXCEEDED_MAX_ORDER_QTY)의 명확한 구별(R1 != R2) 실측
- TEST D: DENY -> APPROVE 전환과 관측값 변화 및 Orchestrator 실행 재개 실측
"""
import unittest
import asyncio
import logging

from main import TradingSystem


class LogCaptureHandler(logging.Handler):
    """실제 Production 런타임 실행 중 발생하는 로그 레코드를 가로채 관측하는 테스트 핸들러."""

    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)

    def get_messages(self):
        return [r.getMessage() for r in self.records]

    def clear(self):
        self.records.clear()


class TestRiskGateObservabilityRejectionReasonOrchestratorActionE2E(unittest.TestCase):
    """RiskGate 판정 결과 관측 및 거부 사유와 Orchestrator 행동의 1:1 연결 E2E 검증."""

    def setUp(self):
        self.log_handler = LogCaptureHandler()
        self.risk_logger = logging.getLogger("option_program.risk_control.risk_engine")
        self.runtime_logger = logging.getLogger("option_program.runtime.program_runtime")
        self.risk_logger.addHandler(self.log_handler)
        self.runtime_logger.addHandler(self.log_handler)

    def tearDown(self):
        self.risk_logger.removeHandler(self.log_handler)
        self.runtime_logger.removeHandler(self.log_handler)

    def test_A_approve_decision_observability_and_orchestrator_execution(self):
        """[TEST A] 정상 Risk 상태 -> RiskGate APPROVE 관측 -> Orchestrator 주문 라우팅 및 Broker 자동 실행 실측."""
        async def _run():
            system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 500_000_000.0})
            await system.initialize()

            # 1. 1 틱 실행
            await system.run_loop(max_ticks=1)

            # [관측 1] 실제 RiskGate 승인 및 주문 생성 관측
            self.assertGreater(len(system.op_runtime.last_orders), 0, "Approved orders must be recorded in runtime last_orders")
            
            # [관측 2] Orchestrator가 승인된 주문을 Broker로 자동 라우팅함 실측
            self.assertGreater(system.orders_routed, 0)
            self.assertGreater(system.executions_handled, 0)

            # [관측 3] 실제 VSSF Position 및 증거금 변동 실측
            self.assertGreater(len(system.vssf.account.get_positions()), 0)
            self.assertGreater(system.vssf.account.used_margin, 0.0)

            await system.shutdown()

        asyncio.run(_run())

    def test_B_deny_decision_rejection_reason_observability_and_1to1_action(self):
        """[TEST B] DENY 판정 + 실제 거부 사유 관측 + Orchestrator 1:1 차단 행동(라우팅 0, Broker 미호출, Mutation = 0) 실측."""
        async def _run():
            system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 500_000_000.0})
            await system.initialize()
            system.op_runtime.risk_config.max_daily_loss_krw = 10_000_000.0

            # Phase 1: 정상 상태 1 틱 실행 -> 승인/체결 확인
            await system.run_loop(max_ticks=1)
            orders_1 = system.orders_routed
            execs_1 = system.executions_handled
            self.assertGreater(orders_1, 0)
            self.assertGreater(execs_1, 0)

            # Phase 2: 일일 손실 한도 초과 주입 (-1500만원 손실)
            system.vssf.account.realized_pnl = -15_000_000.0
            self.log_handler.clear()

            pos_freeze = dict(system.vssf.account.get_positions())
            bal_freeze = system.vssf.account.balance
            exec_reports_freeze = len(system.vssf.execution_engine.reports)

            # Phase 3: 동일 세션 2번째 틱 실행
            await system.run_loop(max_ticks=2)
            self.assertEqual(system.ticks_processed, 2)

            # [관측 1] 실제 RiskGate의 DENY 판정 및 rejection reason 실측
            messages = self.log_handler.get_messages()
            deny_logs = [m for m in messages if "REJECTED:" in m or "Blocked order" in m]
            self.assertGreater(len(deny_logs), 0, "RiskGate DENY logs must be captured during run_loop")
            
            # [관측 2] 관측된 reason에 일일 손실 초과 사유(EXCEEDED_MAX_DAILY_LOSS)가 정확히 포함되어 있는지 실측
            daily_loss_reasons = [m for m in deny_logs if "EXCEEDED_MAX_DAILY_LOSS" in m]
            self.assertGreater(len(daily_loss_reasons), 0, "Observed rejection reason must contain EXCEEDED_MAX_DAILY_LOSS")

            # [관측 3] Orchestrator 1:1 행동 실측: 주문 라우팅 증가 0, 체결 증가 0
            self.assertEqual(system.orders_routed, orders_1)
            self.assertEqual(system.executions_handled, execs_1)

            # [관측 4] VSSF 불변조건 실측: Position/Balance/Reports mutation = 0
            self.assertEqual(dict(system.vssf.account.get_positions()), pos_freeze)
            self.assertEqual(system.vssf.account.balance, bal_freeze)
            self.assertEqual(len(system.vssf.execution_engine.reports), exec_reports_freeze)

            await system.shutdown()

        asyncio.run(_run())

    def test_C_distinct_rejection_reasons_observability(self):
        """[TEST C] 서로 다른 DENY 조건(EXCEEDED_MAX_DAILY_LOSS vs EXCEEDED_MAX_ORDER_QTY)의 사유가 명확히 구별됨(R1 != R2)을 실측."""
        async def _run_condition_1():
            # 조건 1: 일일 손실 한도 초과
            system1 = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 500_000_000.0})
            await system1.initialize()
            system1.op_runtime.risk_config.max_daily_loss_krw = 10_000_000.0
            system1.vssf.account.realized_pnl = -20_000_000.0
            self.log_handler.clear()

            await system1.run_loop(max_ticks=1)
            msgs = self.log_handler.get_messages()
            r1_logs = [m for m in msgs if "REJECTED:" in m]
            self.assertGreater(len(r1_logs), 0)
            reason_1 = r1_logs[0].split("REJECTED: ")[-1]
            await system1.shutdown()
            return reason_1

        async def _run_condition_2():
            # 조건 2: 1회 최대 주문 수량 한도 초과 (max_order_qty = 0)
            system2 = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 500_000_000.0})
            await system2.initialize()
            system2.op_runtime.risk_config.max_order_qty = 0
            self.log_handler.clear()

            await system2.run_loop(max_ticks=1)
            msgs = self.log_handler.get_messages()
            r2_logs = [m for m in msgs if "REJECTED:" in m]
            self.assertGreater(len(r2_logs), 0)
            reason_2 = r2_logs[0].split("REJECTED: ")[-1]
            await system2.shutdown()
            return reason_2

        r1 = asyncio.run(_run_condition_1())
        r2 = asyncio.run(_run_condition_2())

        # [검증 1] 두 거부 사유가 비어있지 않음 확인
        self.assertGreater(len(r1), 0)
        self.assertGreater(len(r2), 0)

        # [검증 2] 서로 다른 DENY 조건의 실제 사유 문자열이 명확하게 구별됨(R1 != R2) 실측
        self.assertIn("EXCEEDED_MAX_DAILY_LOSS", r1)
        self.assertIn("EXCEEDED_MAX_ORDER_QTY", r2)
        self.assertNotEqual(r1, r2, f"Rejection reasons must be distinct: R1='{r1}', R2='{r2}'")

    def test_D_deny_to_approve_recovery_observability_and_orchestrator_resumption(self):
        """[TEST D] DENY -> APPROVE 전환과 관측값 변화 및 Orchestrator 주문/체결 재개 실측."""
        async def _run():
            system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 500_000_000.0})
            await system.initialize()
            system.op_runtime.risk_config.max_daily_loss_krw = 10_000_000.0

            # Phase 1: 위험 상태에서 1번째 틱 실행 -> DENY 관측
            system.vssf.account.realized_pnl = -20_000_000.0
            self.log_handler.clear()
            await system.run_loop(max_ticks=1)

            msgs_p1 = self.log_handler.get_messages()
            deny_logs_p1 = [m for m in msgs_p1 if "EXCEEDED_MAX_DAILY_LOSS" in m]
            self.assertGreater(len(deny_logs_p1), 0, "Phase 1 must observe DENY with EXCEEDED_MAX_DAILY_LOSS")
            self.assertEqual(system.orders_routed, 0)
            self.assertEqual(system.executions_handled, 0)

            # Phase 2: 위험 상태 해제 (손실 리셋: 0원)
            system.vssf.account.realized_pnl = 0.0
            self.log_handler.clear()

            # Phase 3: 동일 세션에서 2번째 틱 실행 -> APPROVE 및 자동 체결 재개 관측
            await system.run_loop(max_ticks=2)
            self.assertEqual(system.ticks_processed, 2)

            # [관측 1] Phase 3에서 Orchestrator 주문 라우팅 건수 증가 관측
            self.assertGreater(system.orders_routed, 0, "Orchestrator must resume routing orders after recovery")

            # [관측 2] Phase 3에서 Broker 체결 자동 실행 및 VSSF 상태 변동 관측
            self.assertGreater(len(system.vssf.execution_engine.reports), 0)
            self.assertGreater(len(system.vssf.account.get_positions()), 0)

            await system.shutdown()

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
