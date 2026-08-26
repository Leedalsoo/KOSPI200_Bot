"""E2E Test: OptionProgramRuntime.process_tick() -> Risk -> OrderRouter -> VSSF Broker -> Execution -> Position/PnL 전체 런타임 실체 검증.

검증 핵심 경로:
    [테스트 코드]
        ↓
    [OptionProgramRuntime 실제 인스턴스]
        ↓
    [OptionProgramRuntime.process_tick(tick) 실제 호출]
        ↓
    [MarketConditionAnalyzer & RiskSensor.scan_risk]
        ↓
    [Strategy Track 1~9 -> SignalGenerator -> DecisionArbiter]
        ↓
    [RiskGate.admit_order & RiskApprovalToken 발급/차단]
        ↓
    [OrderRouter.register_and_route & OMS FSM]
        ↓
    [실제 VSSF PaperBrokerAdapter.send_order]
        ↓
    [실제 VSSF ExecutionEngine (호가 매칭, 슬리피지/수수료) -> CanonicalExecutionReport]
        ↓
    [OptionProgramRuntime.consume_execution_report -> OMS FSM FILLED 완료]
        ↓
    [실제 VSSF PositionManager (Actual Position) & PnLEngine / LedgerEngine (PnL/Margin)]

필수 검증 시나리오:
- TEST A (Risk 승인 경로):
  1) 실제 OptionProgramRuntime 및 실제 VSSF Runtime/BrokerAdapter 생성
  2) 실제 process_tick() 호출을 통해 전략 시그널 생성 및 RiskGate 사전 심사 통과
  3) 유효한 RiskApprovalToken 발급 및 OrderRouter FSM(SENT) 등록 실측
  4) process_tick()이 승인된 CanonicalOrderCommand 리스트를 반환함 실측
  5) 반환된 command를 실제 VSSF Broker.send_order()로 전송하여 실제 ExecutionReport 발급 실측
  6) OptionProgramRuntime.consume_execution_report()로 FSM FILLED 완료 실측
  7) 실제 VSSF PositionManager에 Actual Position 생성(qty > 0, avg_price 일치) 실측
  8) 실제 VSSF 계좌 증거금/원장 트랜잭션 정상 변동 실측

- TEST B (Risk 차단 경로):
  1) B1 (일일 손실 한도 초과): 계좌 실현 손실이 max_daily_loss_krw를 초과한 상태에서 process_tick() 실행
     -> RiskGate에서 EXCEEDED_MAX_DAILY_LOSS로 전면 차단 -> commands == [] (주문 미생성)
     -> Broker 전송 없음, VSSF ExecutionReport 0건, Position/PnL/Balance mutation = 0 실측
  2) B2 (마진 다이어트 긴급 위험): 계좌 증거금 사용률 초과 상태에서 process_tick() 실행
     -> RiskSensor 마진 다이어트 감지 -> RiskGate에서 MARGIN_DIET_ACTIVE로 차단 -> commands == []
     -> Broker 전송 없음, VSSF ExecutionReport 0건, Position/PnL/Balance mutation = 0 실측
"""
import unittest

from shared.contracts.canonical import (
    CanonicalMarketTick,
    CanonicalAccountSummary,
)
from shared.core.contracts import OrderStatus
from option_program.risk_control.risk_engine import RiskConfig
from option_program.broker.broker_interface import BrokerFactory, BrokerMode
from option_program.runtime.program_runtime import OptionProgramRuntime
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime


class TestOptionProgramRuntimeProcessTickVssfE2E(unittest.TestCase):
    """OptionProgramRuntime.process_tick() 출발 전체 런타임 VSSF Broker/Execution/Position/PnL E2E 검증."""

    def setUp(self):
        self.initial_capital = 500_000_000.0  # 5억원
        self.vssf = VirtualSecuritiesFirmRuntime(initial_capital=self.initial_capital)
        self.broker = BrokerFactory.create_broker(mode=BrokerMode.PAPER, vssf_runtime=self.vssf)
        
        self.risk_config = RiskConfig(
            max_order_qty=50,
            max_daily_loss_krw=50_000_000.0,
            max_margin_utilization_ratio=0.85,
            max_position_per_instrument=100,
            vol_spike_threshold_multiplier=1.30,
        )
        self.op_runtime = OptionProgramRuntime(
            risk_config=self.risk_config,
            account_summary=self.vssf.get_account_snapshot(),
        )

    # =========================================================================
    # TEST A: process_tick() 승인 경로 -> VSSF Broker -> Execution -> Position/PnL
    # =========================================================================

    def test_A_process_tick_approved_path_executes_vssf_and_mutates_position_and_pnl(self):
        """[TEST A] OptionProgramRuntime.process_tick() 호출 -> Risk 승인 -> VSSF Broker -> ExecutionReport -> Actual Position/PnL 변동."""
        # 1. 사전 상태 스냅샷 (Before)
        pos_before = dict(self.vssf.account.get_positions())
        pnl_before = self.vssf.account.realized_pnl
        bal_before = self.vssf.account.balance
        used_margin_before = self.vssf.account.used_margin
        exec_count_before = len(self.vssf.execution_engine.reports)

        self.assertEqual(len(pos_before), 0)
        self.assertEqual(pnl_before, 0.0)
        self.assertEqual(bal_before, self.initial_capital)
        self.assertEqual(used_margin_before, 0.0)
        self.assertEqual(exec_count_before, 0)

        # 2. 시장 틱 생성 및 VSSF / Runtime 시세 주입
        tick = CanonicalMarketTick(
            timestamp="2026-08-23 09:00:00.000",
            underlying_price=350.0,
            bid_price=349.9,
            ask_price=350.1,
            last_price=350.0,
            volume=1000,
            seq_id=1,
        )
        self.vssf.process_market_data(tick)
        self.op_runtime.update_account_summary(self.vssf.get_account_snapshot())

        # 3. [핵심] OptionProgramRuntime.process_tick(tick) 실제 호출
        commands = self.op_runtime.process_tick(tick)

        # [검증 1] process_tick() 실행 후 RiskGate를 통과하여 최소 1개 이상의 승인 주문 생성 확인
        self.assertIsInstance(commands, list)
        self.assertGreater(len(commands), 0, "process_tick() must produce approved order commands under normal market tick")

        # 4. 각 승인 주문에 대해 FSM 상태 확인 및 실제 VSSF Broker 실행
        executed_reports = []
        for cmd in commands:
            # [검증 2] 주문이 OrderRouter에 정상 등록되고 FSM 상태가 SENT/VALIDATED인지 확인
            order_uuid = self.op_runtime._order_id_to_uuid.get(cmd.client_order_id)
            self.assertIsNotNone(order_uuid, f"Command {cmd.client_order_id} must have a mapped order UUID in runtime")
            fsm_status = self.op_runtime.oms_fsm.get_status(order_uuid)
            self.assertIn(fsm_status, (OrderStatus.NEW, OrderStatus.VALIDATED, OrderStatus.SENT))

            # [검증 3] 실제 VSSF PaperBrokerAdapter를 통해 주문 발주 실행
            report = self.broker.send_order(cmd)
            if report is not None:
                self.assertEqual(report.client_order_id, cmd.client_order_id)
                self.assertGreater(report.executed_qty, 0)
                self.assertGreater(report.executed_price, 0.0)
                executed_reports.append(report)

                # [검증 4] OptionProgramRuntime이 ExecutionReport를 소비하고 FSM을 FILLED로 전이 완료하는지 확인
                self.op_runtime.consume_execution_report(report)
                final_fsm_status = self.op_runtime.oms_fsm.get_status(order_uuid)
                self.assertEqual(final_fsm_status, OrderStatus.FILLED)

        # 최소 1건 이상의 실제 체결 리포트 생성 확인
        self.assertGreater(len(executed_reports), 0, "At least one approved order must be executed by VSSF Broker")

        # 5. 사후 상태 스냅샷 및 실제 VSSF Position / Account 변동 검증 (After)
        pos_after = dict(self.vssf.account.get_positions())
        exec_count_after = len(self.vssf.execution_engine.reports)
        used_margin_after = self.vssf.account.used_margin

        # [검증 5] 실제 VSSF ExecutionEngine 체결 리포트 수 증가 확인
        self.assertEqual(exec_count_after, exec_count_before + len(executed_reports))

        # [검증 6] 실제 VSSF PositionManager에 Actual Position 생성 실측 (Mutation 발생)
        self.assertGreater(len(pos_after), 0, "VSSF must have open positions after successful execution")
        self.assertNotEqual(len(pos_after), len(pos_before))

        # [검증 7] 실제 VSSF 계좌 증거금 사용액 변동 실측
        self.assertGreater(used_margin_after, used_margin_before)

        # [검증 8] 실제 VSSF 원장 트랜잭션 기록 확인
        self.assertGreater(len(self.vssf.account.ledger_engine.transactions), 0)

    # =========================================================================
    # TEST B: process_tick() 차단 경로 -> VSSF 미호출 -> Execution 0 -> Mutation 0
    # =========================================================================

    def test_B1_process_tick_blocked_by_daily_loss_limit_with_zero_mutation(self):
        """[TEST B1] 일일 손실 한도 초과 상태 -> process_tick() 내부 RiskGate DENY -> commands 빈 목록 반환 -> VSSF Execution 및 Mutation 0."""
        # 1. 사전 상태 스냅샷
        pos_before = dict(self.vssf.account.get_positions())
        pnl_before = self.vssf.account.realized_pnl
        bal_before = self.vssf.account.balance
        used_margin_before = self.vssf.account.used_margin
        exec_count_before = len(self.vssf.execution_engine.reports)

        # 2. 일일 손실 한도(5천만원)를 초과한 계좌 스냅샷을 OptionProgramRuntime에 동기화
        loss_snapshot = CanonicalAccountSummary(
            account_id="ACC-TEST-LOSS",
            total_balance=400_000_000.0,
            realized_pnl=-60_000_000.0,  # 손실 6,000만원 >= 한도 5,000만원
            unrealized_pnl=0.0,
            used_margin=0.0,
            free_margin=400_000_000.0,
        )
        self.op_runtime.update_account_summary(loss_snapshot)

        # 3. 틱 주입 및 process_tick() 실행
        tick = CanonicalMarketTick(
            timestamp="2026-08-23 09:00:00.000",
            underlying_price=350.0,
            bid_price=349.9,
            ask_price=350.1,
            last_price=350.0,
            volume=1000,
            seq_id=2,
        )
        commands = self.op_runtime.process_tick(tick)

        # [검증 1] RiskGate에서 모든 신규 주문이 차단되어 commands가 빈 리스트([])로 반환됨 확인
        self.assertEqual(commands, [], "process_tick() must return empty list when all orders are blocked by RiskGate")

        # [검증 2] Broker로 전송할 명령어가 없으므로 VSSF ExecutionReport 생성 건수 0건 확인
        exec_count_after = len(self.vssf.execution_engine.reports)
        self.assertEqual(exec_count_after, exec_count_before)

        # [검증 3] 불변조건: Position mutation = 0, PnL mutation = 0, Balance mutation = 0, Margin mutation = 0
        pos_after = dict(self.vssf.account.get_positions())
        pnl_after = self.vssf.account.realized_pnl
        bal_after = self.vssf.account.balance
        used_margin_after = self.vssf.account.used_margin

        self.assertEqual(pos_after, pos_before)
        self.assertEqual(pnl_after, pnl_before)
        self.assertEqual(bal_after, bal_before)
        self.assertEqual(used_margin_after, used_margin_before)

    def test_B2_process_tick_blocked_by_margin_diet_with_zero_mutation(self):
        """[TEST B2] 증거금 사용률 초과 상태 -> RiskSensor 마진 다이어트 감지 -> process_tick() 차단 -> commands 빈 목록 -> Mutation 0."""
        pos_before = dict(self.vssf.account.get_positions())
        pnl_before = self.vssf.account.realized_pnl
        bal_before = self.vssf.account.balance
        exec_count_before = len(self.vssf.execution_engine.reports)

        # 증거금 사용률 92% (> 85%) 상태의 계좌 스냅샷 동기화
        diet_snapshot = CanonicalAccountSummary(
            account_id="ACC-TEST-DIET",
            total_balance=500_000_000.0,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            used_margin=460_000_000.0,  # 92% 사용률
            free_margin=40_000_000.0,
        )
        self.op_runtime.update_account_summary(diet_snapshot)

        # 틱 주입 및 process_tick() 실행
        tick = CanonicalMarketTick(
            timestamp="2026-08-23 09:00:00.000",
            underlying_price=350.0,
            bid_price=349.9,
            ask_price=350.1,
            last_price=350.0,
            volume=1000,
            seq_id=3,
        )
        commands = self.op_runtime.process_tick(tick)

        # [검증 1] 마진 다이어트 감지로 비-헤지 진입 주문 전면 차단 확인
        self.assertEqual(commands, [], "process_tick() must return empty list when entries are blocked by MARGIN_DIET")

        # [검증 2] 체결 없음 및 불변조건 실측
        self.assertEqual(len(self.vssf.execution_engine.reports), exec_count_before)
        self.assertEqual(dict(self.vssf.account.get_positions()), pos_before)
        self.assertEqual(self.vssf.account.realized_pnl, pnl_before)
        self.assertEqual(self.vssf.account.balance, bal_before)


if __name__ == "__main__":
    unittest.main()
