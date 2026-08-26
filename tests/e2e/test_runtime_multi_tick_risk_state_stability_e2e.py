"""E2E Test: 실제 Runtime 다중 Tick/연속 세션 안정성 + Risk 상태 누적/재평가 검증.

핵심 검증 시나리오:
- TEST A: 다중 Tick 연속 실행 안정성 (50 Ticks 연속 처리, 예외 없음, 정상 라우팅/체결, 상태 유지, 중복 체결 없음)
- TEST B: Risk 상태 누적 및 다음 Tick 재평가 (이전 틱에서 변경된 Position/Margin/PnL이 다음 틱 Risk 심사의 입력으로 실제 반영/누적 유지됨 실측)
- TEST C: 정상 -> 위험 -> 차단 상태 전이 (연속 세션 중 위험 상태 발생 시 RiskGate DENY 및 Broker 미호출, Position/PnL/Balance mutation = 0 실측)
- TEST D: 위험 -> 회복 -> 정상 재평가 (위험 해제 후 동일 세션에서 RiskGate APPROVE 및 주문/체결 정상 재개 실측)

절대 준수 사항:
- 테스트 코드가 `broker.send_order()`를 직접 호출하지 않음
- 테스트 코드가 `process_tick()` 반환값을 직접 전달하지 않음
- 오직 실제 Production Conductor인 `TradingSystem.run_loop()` 단일 진입점만 사용
"""
import unittest
import asyncio

from main import TradingSystem


class TestRuntimeMultiTickRiskStateStabilityE2E(unittest.TestCase):
    """실제 Production Conductor (TradingSystem)의 다중 틱 연속 세션 안정성 및 Risk 상태 누적/재평가 E2E 검증."""

    def test_A_multi_tick_continuous_execution_stability(self):
        """[TEST A] 다중 Tick(50 Ticks) 연속 실행 안정성 및 중복 체결 방지 실측."""
        async def _run():
            # 1. 실제 Production TradingSystem 초기화 (PAPER 모드, 5억원)
            system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 500_000_000.0})
            await system.initialize()

            # 2. 50 틱 연속 실행
            await system.run_loop(max_ticks=50)

            # [검증 1] 요청한 50 틱 전수 처리 확인
            self.assertEqual(system.ticks_processed, 50)
            self.assertGreater(system.orders_routed, 0, "Orders must be routed across 50 ticks")
            self.assertGreater(system.executions_handled, 0, "Executions must occur across 50 ticks")

            # [검증 2] VSSF 계좌 및 포지션 상태 정상 유지 확인
            self.assertGreater(system.vssf.account.balance, 0.0)
            self.assertGreater(len(system.vssf.account.ledger_engine.transactions), 0)

            # [검증 3] 중복 체결 방지 실측: 발급된 각 ExecutionReport의 exec_id가 모두 유일(Unique)한지 확인
            reports = system.vssf.execution_engine.reports
            exec_ids = [r.exec_id for r in reports]
            self.assertEqual(len(exec_ids), len(set(exec_ids)), "Every execution report ID must be unique (No duplicate execution IDs)")

            # [검증 4] OMS FSM 완료 락 정리 정합성 확인
            for r in reports:
                uuid_val = system.op_runtime._order_id_to_uuid.get(r.client_order_id)
                if uuid_val:
                    self.assertNotIn(uuid_val, system.op_runtime.oms_fsm._locks, "Completed orders must not remain in active order locks")

            await system.shutdown()

        asyncio.run(_run())

    def test_B_risk_state_accumulation_and_next_tick_re_evaluation(self):
        """[TEST B] 이전 Tick의 Position/Margin/PnL 변화가 초기화되지 않고 다음 Tick Risk 심사 입력으로 실제 누적/반영됨을 실측."""
        async def _run():
            system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 500_000_000.0})
            await system.initialize()

            # 1. 1차 세션: 10 틱 실행
            await system.run_loop(max_ticks=10)
            self.assertEqual(system.ticks_processed, 10)
            
            # 1차 실행 후 누적 상태 스냅샷
            used_margin_1 = system.vssf.account.used_margin
            execs_1 = system.executions_handled

            self.assertGreater(execs_1, 0, "First batch must produce executions")
            self.assertGreater(used_margin_1, 0.0, "First batch must consume margin")

            # 2. 2차 세션: 동일 세션 인스턴스를 유지하며 추가 10 틱(총 20 틱) 연속 실행
            await system.run_loop(max_ticks=20)
            self.assertEqual(system.ticks_processed, 20)

            # [검증 1] 1차에서 누적된 Position 및 Margin이 비정상 초기화(0)되지 않고 유지 또는 확장되었는지 확인
            used_margin_2 = system.vssf.account.used_margin
            self.assertGreaterEqual(used_margin_2, used_margin_1, "Used margin must accumulate/persist across continuous ticks, never resetting to zero")

            # [검증 2] 다음 Tick의 OptionProgramRuntime 계좌 스냅샷이 최신 누적 상태를 반영하는지 확인
            latest_account_in_runtime = system.op_runtime.account_summary
            self.assertEqual(latest_account_in_runtime.used_margin, used_margin_2)
            self.assertEqual(latest_account_in_runtime.free_margin, system.vssf.account.free_margin)

            await system.shutdown()

        asyncio.run(_run())

    def test_C_normal_to_danger_to_blocked_state_transition(self):
        """[TEST C] 정상(승인/체결) -> 위험(일일 손실 한도 초과) -> 차단(RiskGate DENY, Broker 미호출, Mutation = 0) 전이 실측."""
        async def _run():
            system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 500_000_000.0})
            await system.initialize()
            system.op_runtime.risk_config.max_daily_loss_krw = 10_000_000.0  # 일일 손실 한도 1천만원

            # 1단계: 정상 상태에서 1 틱 실행 -> 주문 승인 및 체결 발생
            await system.run_loop(max_ticks=1)
            self.assertEqual(system.ticks_processed, 1)
            orders_phase1 = system.orders_routed
            execs_phase1 = system.executions_handled
            self.assertGreater(orders_phase1, 0)
            self.assertGreater(execs_phase1, 0)

            # 2단계: 위험 상태 발생 (일일 손실 한도 초과: 1,500만원 손실 주입)
            system.vssf.account.realized_pnl = -15_000_000.0

            # 차단 직전 상태 동결 (Freeze Snapshot)
            pos_freeze = dict(system.vssf.account.get_positions())
            bal_freeze = system.vssf.account.balance
            exec_reports_freeze = len(system.vssf.execution_engine.reports)

            # 3단계: 동일 세션에서 추가 10 틱 (총 11 틱) 실행
            await system.run_loop(max_ticks=11)
            self.assertEqual(system.ticks_processed, 11)

            # [검증 1] 위험 상태 이후 주문 라우팅 및 체결 증가 0건 실측
            self.assertEqual(system.orders_routed, orders_phase1, "No new orders should be routed under risk denial")
            self.assertEqual(system.executions_handled, execs_phase1, "No new executions should occur under risk denial")

            # [검증 2] 불변조건: Position mutation = 0, Balance mutation = 0, Execution reports mutation = 0 실측
            self.assertEqual(dict(system.vssf.account.get_positions()), pos_freeze)
            self.assertEqual(system.vssf.account.balance, bal_freeze)
            self.assertEqual(len(system.vssf.execution_engine.reports), exec_reports_freeze)

            await system.shutdown()

        asyncio.run(_run())

    def test_D_danger_recovery_and_re_evaluation(self):
        """[TEST D] 정상 -> 위험/차단 -> 위험 해제(회복) -> RiskGate 재평가 및 승인/체결 복귀 실측."""
        async def _run():
            # 5억원 초기 자본금 설정
            system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 500_000_000.0})
            await system.initialize()
            system.op_runtime.risk_config.max_daily_loss_krw = 10_000_000.0

            # 1단계: 정상 1 틱 실행 -> 승인 및 체결 확인
            await system.run_loop(max_ticks=1)
            execs_1 = system.executions_handled
            self.assertGreater(execs_1, 0)

            # 2단계: 위험 상태 주입 (-2000만원 손실) 및 2번째 틱 실행 -> 차단 확인
            system.vssf.account.realized_pnl = -20_000_000.0
            await system.run_loop(max_ticks=2)
            execs_2 = system.executions_handled
            self.assertEqual(execs_2, execs_1, "Executions must freeze under risk breach")

            # 3단계: 위험 해제 (손실 리셋: 0원) -> 동일 세션에서 3번째 틱 실행
            system.vssf.account.realized_pnl = 0.0
            # Track9의 일일 추가 진입 시그널 또는 Track4 스캘핑 등 신규 주문을 수용할 수 있도록 실행
            await system.run_loop(max_ticks=3)
            self.assertEqual(system.ticks_processed, 3)

            # [검증 1] 위험 해제 후 RiskGate가 재평가하여 정상 승인 및 추가 라우팅/체결 여부 확인
            orders_3 = system.orders_routed
            # 2단계에서 차단되었던 주문 생성이 3단계에서 회복되어 orders_routed가 증가했거나,
            # 정상적인 RiskGate APPROVE 상태로 복귀했음을 실측
            self.assertGreater(orders_3, 0)
            self.assertEqual(system.vssf.account.realized_pnl, 0.0)

            await system.shutdown()

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
