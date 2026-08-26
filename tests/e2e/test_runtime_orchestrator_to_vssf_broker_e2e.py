"""E2E Test: Production Runtime Orchestrator (TradingSystem) -> VSSF Broker 자동 연결 실체 검증.

핵심 검증 대상:
    [실제 Production Orchestrator 진입점: TradingSystem.run_loop()]
        ↓ (내부 자동 호출)
    [실제 OptionProgramRuntime.process_tick()]
        ↓ (내부 자동 반환)
    [실제 TradingSystem 루프가 반환된 CanonicalOrderCommand 수령]
        ↓ (내부 자동 호출)
    [실제 VSSF PaperBrokerAdapter.send_order()]
        ↓ (내부 자동 매칭)
    [실제 VSSF ExecutionEngine -> CanonicalExecutionReport]
        ↓ (내부 자동 호출)
    [실제 OptionProgramRuntime.consume_execution_report() -> FSM 완료]
        ↓ (내부 자동 반영)
    [실제 VSSF PositionManager (Actual Position) & PnLEngine / LedgerEngine]

절대 준수 사항:
- 테스트 코드가 직접 `broker.send_order()`를 호출하지 않음
- 테스트 코드가 직접 `ExecutionEngine.execute_order()`를 호출하지 않음
- 테스트 코드가 직접 `PositionManager.update_position()`을 호출하지 않음
- 테스트 코드는 오직 실제 Production 진입점인 `TradingSystem.run_loop()`만 실행하고 결과를 관찰함
"""
import unittest
import asyncio

from main import TradingSystem


class TestRuntimeOrchestratorToVssfBrokerE2E(unittest.TestCase):
    """실제 Production Conductor (TradingSystem)를 통한 VSSF Broker 자동 연결 E2E 검증."""

    def test_01_orchestrator_run_loop_automatically_routes_to_broker_and_mutates_vssf(self):
        """[TEST 1] TradingSystem.run_loop() 단일 진입점 실행 -> 내부에서 process_tick() 주문을 Broker.send_order()로 자동 연결 및 체결/포지션 변동 실측."""
        async def _run():
            # 1. 실제 Production Conductor 초기화 (PAPER 모드, 5천만원)
            system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 50_000_000.0})
            await system.initialize()

            # 2. 사전 상태 확인
            self.assertEqual(system.ticks_processed, 0)
            self.assertEqual(system.orders_routed, 0)
            self.assertEqual(system.executions_handled, 0)
            self.assertEqual(len(system.vssf.account.get_positions()), 0)
            self.assertEqual(len(system.vssf.account.ledger_engine.transactions), 0)

            # 3. [핵심] 테스트 코드는 broker.send_order를 절대 호출하지 않고, 오직 Production Orchestrator의 run_loop만 실행
            await system.run_loop(max_ticks=20)

            # 4. 자동 연동 실측 검증
            # [검증 1] Orchestrator가 지정된 틱(20틱)을 전수 처리했는지 확인
            self.assertGreaterEqual(system.ticks_processed, 20)

            # [검증 2] process_tick()이 반환한 주문을 Orchestrator가 Broker로 자동 라우팅했는지 확인
            self.assertGreater(system.orders_routed, 0, "TradingSystem must automatically route order commands returned by process_tick()")

            # [검증 3] Broker.send_order()를 통해 실제 체결 및 리포트가 Orchestrator 내부에서 자동 처리되었는지 확인
            self.assertGreater(system.executions_handled, 0, "TradingSystem must automatically handle executions returned by Broker")

            # [검증 4] 실제 VSSF PositionManager에 Actual Position이 자동 생성되었거나, 체결 이력이 기록되었는지 확인
            self.assertGreater(len(system.vssf.execution_engine.reports), 0)
            self.assertGreater(len(system.vssf.account.ledger_engine.transactions), 0)
            self.assertGreater(system.vssf.account.balance, 0.0)

            # 5. 시스템 정상 종료
            await system.shutdown()

        asyncio.run(_run())

    def test_02_orchestrator_run_loop_with_risk_denial_blocks_broker_with_zero_mutation(self):
        """[TEST 2] TradingSystem.run_loop() 실행 중 Risk 차단 발생 -> commands 미생성 -> Broker 미호출 및 Mutation 0 자동 유지 실측."""
        async def _run():
            # 1. 실제 Production Conductor 초기화
            system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 50_000_000.0})
            await system.initialize()

            # 2. VSSF 계좌에 일일 손실 한도 초과 상태 주입 (모든 진입 차단 유도)
            system.vssf.account.realized_pnl = -20_000_000.0  # 2천만원 손실
            system.op_runtime.risk_config.max_daily_loss_krw = 10_000_000.0  # 한도 1천만원

            pos_before = dict(system.vssf.account.get_positions())
            bal_before = system.vssf.account.balance
            exec_count_before = len(system.vssf.execution_engine.reports)

            # 3. Production Orchestrator run_loop 실행 (테스트 코드는 수동 개입 없음)
            await system.run_loop(max_ticks=10)

            # 4. 차단 및 Mutation = 0 실측 검증
            # [검증 1] RiskGate 차단으로 주문 라우팅 0건 확인
            self.assertEqual(system.orders_routed, 0, "Orders must be blocked by RiskGate before broker routing")
            self.assertEqual(system.executions_handled, 0)

            # [검증 2] VSSF 불변조건 실측 (Position/PnL/Balance mutation = 0)
            self.assertEqual(len(system.vssf.execution_engine.reports), exec_count_before)
            self.assertEqual(dict(system.vssf.account.get_positions()), pos_before)
            self.assertEqual(system.vssf.account.balance, bal_before)

            # 5. 시스템 정상 종료
            await system.shutdown()

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
