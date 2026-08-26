"""E2E Test: Risk 상태 변화 -> RiskGate 판정 변화 -> Production Orchestrator (TradingSystem) Broker 자동 실행/차단 인과관계 실체 검증.

검증 인과관계 경로:
    [Risk 상태 입력 (Account / Position / Market Data)]
        ↓
    [RiskSensor.scan_risk & RiskEngine.evaluate_order 실시간 재평가]
        ↓
    [RiskGate.admit_order 판정 변화 (APPROVE <-> DENY)]
        ↓
    [OptionProgramRuntime.process_tick() commands 반환 여부 변화]
        ↓
    [실제 Production Orchestrator: TradingSystem.run_loop()]
        ↓
    [승인 시 Broker 자동 발주 / 차단 시 Broker 자동 미호출]
        ↓
    [실제 VSSF ExecutionEngine -> CanonicalExecutionReport]
        ↓
    [실제 VSSF PositionManager (Actual Position) & PnLEngine / LedgerEngine]

4대 핵심 검증 시나리오:
- TEST A: 정상 Risk 상태 -> RiskGate APPROVE -> Orchestrator 주문 자동 라우팅 및 Broker 체결 -> Actual Position/Account mutation 실측
- TEST B: 정상 -> 위험 상태 변화 -> RiskGate APPROVE -> DENY 판정 변화 -> Orchestrator 주문 라우팅 중단 -> Broker 미호출 및 Mutation = 0 실측
- TEST C: 위험 상태 유지 -> 5 Ticks 연속 실행 동안 지속 DENY -> 매 틱 주문/체결/포지션/손익/마진 증가 0건 실측
- TEST D: 위험 -> 정상 회복 -> RiskGate DENY -> APPROVE 판정 복귀 -> Orchestrator 주문 라우팅 및 Broker 체결 재개 -> Mutation 발생 실측

절대 준수 사항:
- 테스트 코드가 `broker.send_order()`를 직접 호출하지 않음
- 테스트 코드가 `RiskGate.admit_order()`를 직접 호출하여 판정만 조작하지 않음
- 테스트 코드가 `process_tick()` 반환값을 직접 Broker로 전달하지 않음
- 오직 실제 Production Conductor인 `TradingSystem.run_loop()` 단일 진입점만 사용
"""
import unittest
import asyncio

from main import TradingSystem


class TestRiskStateToRiskGateOrchestratorCausalityE2E(unittest.TestCase):
    """Risk 상태 변화와 RiskGate 판정, Production Orchestrator Broker 자동 실행/차단의 엄밀한 인과관계 E2E 검증."""

    def test_A_normal_risk_state_approves_and_orchestrator_automatically_executes(self):
        """[TEST A] 정상 Risk 상태 -> RiskGate APPROVE -> TradingSystem이 Broker.send_order() 자동 실행 -> Actual Position/Account 변동 실측."""
        async def _run():
            # 1. Production Orchestrator 초기화 (5억원 초기 자본금)
            system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 500_000_000.0})
            await system.initialize()

            # 2. 초기 상태 스냅샷
            self.assertEqual(system.orders_routed, 0)
            self.assertEqual(system.executions_handled, 0)
            self.assertEqual(len(system.vssf.account.get_positions()), 0)
            self.assertEqual(len(system.vssf.execution_engine.reports), 0)

            # 3. [핵심] Orchestrator 진입점 실행 (1 틱)
            await system.run_loop(max_ticks=1)

            # [인과관계 실측 1] 정상 상태에서 process_tick() 내부 RiskGate가 승인하여 Orchestrator가 주문을 자동 라우팅함
            self.assertGreater(system.orders_routed, 0, "Orchestrator must automatically route approved orders")

            # [인과관계 실측 2] Orchestrator가 Broker.send_order()를 자동 호출하여 체결을 수령함
            self.assertGreater(system.executions_handled, 0, "Orchestrator must automatically process broker executions")

            # [인과관계 실측 3] 실제 VSSF PositionManager에 Actual Position 생성 확인
            self.assertGreater(len(system.vssf.account.get_positions()), 0, "VSSF PositionManager must have open positions")

            # [인과관계 실측 4] 실제 계좌 증거금 점유 및 원장 트랜잭션 기록 확인
            self.assertGreater(system.vssf.account.used_margin, 0.0)
            self.assertGreater(len(system.vssf.account.ledger_engine.transactions), 0)

            await system.shutdown()

        asyncio.run(_run())

    def test_B_normal_to_danger_transition_causes_deny_and_orchestrator_blocks(self):
        """[TEST B] 정상 -> 위험 상태 변화 -> RiskGate DENY 전이 -> Orchestrator 주문 라우팅 중단 및 Broker 미호출, Mutation = 0 실측."""
        async def _run():
            system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 500_000_000.0})
            await system.initialize()
            system.op_runtime.risk_config.max_daily_loss_krw = 10_000_000.0  # 한도 1천만원

            # Phase 1: 정상 상태에서 1 틱 실행 -> 승인 및 체결 발생 확인
            await system.run_loop(max_ticks=1)
            orders_phase1 = system.orders_routed
            execs_phase1 = system.executions_handled
            self.assertGreater(orders_phase1, 0)
            self.assertGreater(execs_phase1, 0)

            # Phase 2: Risk 입력 상태 변화 (일일 손실 한도 초과: 1,500만원 손실 발생)
            system.vssf.account.realized_pnl = -15_000_000.0

            # 상태 동결 스냅샷 (Freeze Snapshot)
            pos_freeze = dict(system.vssf.account.get_positions())
            bal_freeze = system.vssf.account.balance
            used_margin_freeze = system.vssf.account.used_margin
            exec_reports_freeze = len(system.vssf.execution_engine.reports)

            # Phase 3: 동일 세션에서 2번째 틱 실행
            await system.run_loop(max_ticks=2)
            self.assertEqual(system.ticks_processed, 2)

            # [인과관계 실측 1] 위험 상태 주입 후 RiskGate가 DENY하여 Orchestrator 주문 라우팅 건수가 증가하지 않음 (delta = 0)
            self.assertEqual(system.orders_routed, orders_phase1, "Orders routed must not increase under risk breach")

            # [인과관계 실측 2] Broker가 호출되지 않아 체결 건수 증가 0 (delta = 0)
            self.assertEqual(system.executions_handled, execs_phase1, "Executions must not increase under risk breach")

            # [인과관계 실측 3] VSSF 불변조건: Position mutation = 0, Balance mutation = 0, Used Margin mutation = 0, Reports = 0
            self.assertEqual(dict(system.vssf.account.get_positions()), pos_freeze)
            self.assertEqual(system.vssf.account.balance, bal_freeze)
            self.assertEqual(system.vssf.account.used_margin, used_margin_freeze)
            self.assertEqual(len(system.vssf.execution_engine.reports), exec_reports_freeze)

            await system.shutdown()

        asyncio.run(_run())

    def test_C_continuous_danger_state_maintains_deny_across_multiple_ticks(self):
        """[TEST C] 위험 상태 유지 -> 5 Ticks 연속 실행 동안 지속 DENY -> 매 틱 주문/체결/상태 증가 0건 불변 실측."""
        async def _run():
            system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 500_000_000.0})
            await system.initialize()
            system.op_runtime.risk_config.max_daily_loss_krw = 10_000_000.0

            # 1. 초기 위험 상태 주입 (-2,000만원 손실)
            system.vssf.account.realized_pnl = -20_000_000.0

            pos_before = dict(system.vssf.account.get_positions())
            bal_before = system.vssf.account.balance
            exec_count_before = len(system.vssf.execution_engine.reports)
            margin_before = system.vssf.account.used_margin

            # 2. 위험 상태를 유지한 채 5 Ticks 연속 실행
            await system.run_loop(max_ticks=5)
            self.assertEqual(system.ticks_processed, 5)

            # [인과관계 실측 1] 5 Ticks 내내 매 틱 RiskGate가 DENY하여 전체 주문 라우팅 = 0건
            self.assertEqual(system.orders_routed, 0, "All 5 ticks must be blocked by RiskGate")

            # [인과관계 실측 2] 전체 체결 처리 = 0건
            self.assertEqual(system.executions_handled, 0, "No executions should be handled across 5 blocked ticks")

            # [인과관계 실측 3] VSSF 상태 전수 0 변동 (Position/PnL/Balance/Margin mutation = 0)
            self.assertEqual(dict(system.vssf.account.get_positions()), pos_before)
            self.assertEqual(system.vssf.account.balance, bal_before)
            self.assertEqual(system.vssf.account.used_margin, margin_before)
            self.assertEqual(len(system.vssf.execution_engine.reports), exec_count_before)

            await system.shutdown()

        asyncio.run(_run())

    def test_D_danger_to_recovery_causes_riskgate_approve_and_orchestrator_resumes(self):
        """[TEST D] 위험 -> 정상 회복 -> RiskGate DENY -> APPROVE 전이 -> Orchestrator 주문 라우팅 및 Broker 체결 정상 재개 실측."""
        async def _run():
            system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 500_000_000.0})
            await system.initialize()
            system.op_runtime.risk_config.max_daily_loss_krw = 10_000_000.0

            # Phase 1: 위험 상태에서 1번째 틱 실행 -> 차단 확인
            system.vssf.account.realized_pnl = -20_000_000.0
            await system.run_loop(max_ticks=1)
            self.assertEqual(system.ticks_processed, 1)
            self.assertEqual(system.orders_routed, 0, "Must be blocked in Phase 1")
            self.assertEqual(system.executions_handled, 0)

            # Phase 2: Risk 상태 회복 (손실 0원 리셋)
            system.vssf.account.realized_pnl = 0.0

            # Phase 3: 동일 Orchestrator에서 2번째 틱 실행
            await system.run_loop(max_ticks=2)
            self.assertEqual(system.ticks_processed, 2)

            # [인과관계 실측 1] 손실 해제 후 RiskGate가 재평가하여 APPROVE로 전이 -> Orchestrator 주문 라우팅 재개 (orders_routed > 0)
            self.assertGreater(system.orders_routed, 0, "Orchestrator must resume routing orders after risk recovery")

            # [인과관계 실측 2] Broker.send_order() 자동 체결 재개 (executions_handled > 0)
            self.assertGreater(system.executions_handled, 0, "Orchestrator must resume handling executions after risk recovery")

            # [인과관계 실측 3] Actual Position 및 계좌 증거금 변동 실측
            self.assertGreater(len(system.vssf.account.get_positions()), 0)
            self.assertGreater(system.vssf.account.used_margin, 0.0)

            await system.shutdown()

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
