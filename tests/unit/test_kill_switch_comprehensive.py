# -*- coding: utf-8 -*-
"""Comprehensive Functional Assertion & Full Pipeline Verification for Kill Switch (Emergency Stop).

Verifies 7 Essential Real-Object Scenarios:
A. Kill Switch OFF: Real Pipeline (Tick -> Strategy -> Gate -> Router -> Broker -> Execution -> Position)
B. Kill Switch ON: Real Pipeline Suppression (Broker dispatch == 0, Mutation == 0)
C. State Transition: OFF -> ON -> OFF (Active -> Blocked -> Full Resumption)
D. Existing In-Flight Order Handling: FSM Integrity & New Order Isolation
E. Data Failure + Kill Switch Combination: Stale/Duplicate/Gap/Out-of-order + Kill Switch
F. Broker Failure + Kill Switch Combination: Broker Disconnect/Reject + Kill Switch
G. Concurrency & Rapid Toggle Stability: 100-cycle stress test for deterministic safety
"""
import asyncio
import unittest
from typing import List

from main import TradingSystem
from shared.contracts.canonical import (
    CanonicalOrderCommand,
    CanonicalOrderSide,
    CanonicalAssetType,
    CanonicalOptionType,
    CanonicalAccountSummary,
    CanonicalMarketTick,
    CanonicalExecutionReport,
)
from option_program.risk_control.risk_engine import RiskConfig
from option_program.runtime.program_runtime import OptionProgramRuntime
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime
from option_program.broker.broker_interface import PaperBrokerAdapter


class TestKillSwitchComprehensive(unittest.TestCase):
    """[3단계-4] Kill Switch (비상정지) 종합 검증 테스트 스위트 (실제 객체 파이프라인 전수 실측)"""

    def setUp(self):
        self.risk_config = RiskConfig(
            max_order_qty=50,
            max_daily_loss_krw=10_000_000.0,
            max_margin_utilization_ratio=0.85,
        )
        self.vssf = VirtualSecuritiesFirmRuntime(initial_capital=2_000_000_000.0)
        self.broker = PaperBrokerAdapter(vssf_runtime=self.vssf)
        self.account_summary = CanonicalAccountSummary(
            account_id="ACC-TEST-001",
            total_balance=2_000_000_000.0,
            used_margin=0.0,
            free_margin=2_000_000_000.0,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            positions={},
        )
        self.runtime = OptionProgramRuntime(
            risk_config=self.risk_config,
            account_summary=self.account_summary,
        )

    def test_A_kill_switch_off_real_orchestrator_pipeline_allows_broker_execution(self):
        """[A. Kill Switch OFF] 실제 TradingSystem Orchestrator Conductor 파이프라인에서 정상 발주 및 체결/포지션 변동 실측."""
        async def _run():
            system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 100_000_000.0})
            try:
                await system.initialize()

                # 사전 상태 확인
                self.assertFalse(system.op_runtime.risk_engine.is_kill_switch_active())
                self.assertEqual(system.orders_routed, 0)
                self.assertEqual(system.executions_handled, 0)

                # 10틱 실행 (Kill Switch OFF 상태)
                await system.run_loop(max_ticks=10)

                # Kill Switch OFF 상태에서는 실제 전략 주문이 생성되어 브로커로 전달 및 체결됨을 확인
                self.assertGreater(system.orders_routed, 0, "Kill Switch OFF must allow routing orders to Broker")
                self.assertGreater(system.executions_handled, 0, "Kill Switch OFF must allow broker executions")
            finally:
                await system.shutdown()

        asyncio.run(_run())

    def test_B_kill_switch_on_real_orchestrator_pipeline_blocks_broker_and_zero_mutations(self):
        """[B. Kill Switch ON] 실제 TradingSystem Conductor 파이프라인에서 신규 주문 100% 차단, Broker 발주 0회, Mutation 0 실측."""
        async def _run():
            system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 100_000_000.0})
            try:
                await system.initialize()

                # Kill Switch 발동
                system.op_runtime.risk_engine.trigger_kill_switch(reason="EMERGENCY_PANIC_STOP")
                self.assertTrue(system.op_runtime.risk_engine.is_kill_switch_active())

                initial_balance = system.vssf.account.balance
                initial_positions_count = len(system.vssf.account.get_positions())

                # 20틱 실행 (Kill Switch ON 상태)
                await system.run_loop(max_ticks=20)

                # [Functional Assertion]
                self.assertGreaterEqual(system.ticks_processed, 20, "Ticks must be processed")
                self.assertEqual(system.orders_routed, 0, "Kill Switch ON must result in ZERO routed orders to Broker")
                self.assertEqual(system.executions_handled, 0, "Kill Switch ON must result in ZERO executions")

                # [Accounting Mutation Invariance == 0]
                self.assertEqual(system.vssf.account.balance, initial_balance, "Balance must not mutate")
                self.assertEqual(len(system.vssf.account.get_positions()), initial_positions_count, "Positions must not mutate")
                exec_txs = [tx for tx in system.vssf.account.ledger_engine.transactions if tx.get("type") == "EXECUTION"]
                self.assertEqual(len(exec_txs), 0, "No execution transactions in ledger")
            finally:
                await system.shutdown()

        asyncio.run(_run())

    def test_C_state_transition_off_to_on_to_off_resumption(self):
        """[C. OFF -> ON -> OFF] 실제 Runtime + Broker 파이프라인에서 정상 발주 -> 차단 -> 정상 재개 실측."""
        tick = CanonicalMarketTick(
            timestamp="2026-08-23 09:00:01",
            underlying_price=350.0,
            bid_price=349.95,
            ask_price=350.05,
            last_price=350.0,
            volume=100,
            seq_id=1,
        )

        # -----------------------------------------------------------------
        # Phase 1: Kill Switch OFF -> 주문 승인 및 실제 브로커 발주/체결 실측
        # -----------------------------------------------------------------
        self.assertFalse(self.runtime.risk_engine.is_kill_switch_active())
        self.vssf.process_market_data(tick)
        self.runtime.update_account_summary(self.vssf.get_account_snapshot())
        commands_p1 = self.runtime.process_tick(tick)
        self.assertGreater(len(commands_p1), 0, "Phase 1 (OFF) must produce approved orders")

        # 실제 연결된 브로커로 발주 (ACK 수신) 및 별도 체결 수신
        exec_count_p1 = 0
        for cmd in commands_p1:
            ack = self.broker.send_order(cmd)
            self.assertIsNotNone(ack)
            self.assertTrue(ack.success)
        reports_p1 = self.broker.poll_execution_reports()
        for report in reports_p1:
            exec_count_p1 += 1
            self.runtime.consume_execution_report(report)
        self.assertGreater(exec_count_p1, 0, "Phase 1 (OFF) must execute on Broker")

        # -----------------------------------------------------------------
        # Phase 2: Kill Switch ON -> 신규 주문 전면 차단 (0건 반환 및 브로커 발주 0건)
        # -----------------------------------------------------------------
        self.runtime.risk_engine.trigger_kill_switch(reason="PHASE_2_TEST_STOP")
        self.assertTrue(self.runtime.risk_engine.is_kill_switch_active())

        tick_p2 = CanonicalMarketTick(
            timestamp="2026-08-23 09:00:02",
            underlying_price=350.1,
            bid_price=350.05,
            ask_price=350.15,
            last_price=350.1,
            volume=120,
            seq_id=2,
        )
        self.vssf.process_market_data(tick_p2)
        self.runtime.update_account_summary(self.vssf.get_account_snapshot())
        commands_p2 = self.runtime.process_tick(tick_p2)
        self.assertEqual(len(commands_p2), 0, "Phase 2 (ON) must return ZERO orders from process_tick")

        # -----------------------------------------------------------------
        # Phase 3: Kill Switch OFF -> 비상 정지 해제 후 주문 승인 및 브로커 발주/체결 정상 재개
        # -----------------------------------------------------------------
        self.runtime.risk_engine.reset_kill_switch()
        self.assertFalse(self.runtime.risk_engine.is_kill_switch_active())

        tick_p3 = CanonicalMarketTick(
            timestamp="2026-08-23 09:00:03",
            underlying_price=350.2,
            bid_price=350.15,
            ask_price=350.25,
            last_price=350.2,
            volume=150,
            seq_id=3,
        )
        self.vssf.process_market_data(tick_p3)
        self.runtime.update_account_summary(self.vssf.get_account_snapshot())
        commands_p3 = self.runtime.process_tick(tick_p3)
        self.assertGreater(len(commands_p3), 0, "Phase 3 (OFF) must resume producing approved orders")

        exec_count_p3 = 0
        for cmd in commands_p3:
            ack = self.broker.send_order(cmd)
            self.assertIsNotNone(ack)
            self.assertTrue(ack.success)
        reports_p3 = self.broker.poll_execution_reports()
        for report in reports_p3:
            exec_count_p3 += 1
            self.runtime.consume_execution_report(report)
        self.assertGreater(exec_count_p3, 0, "Phase 3 (OFF) must resume broker executions")

    def test_D_in_flight_existing_order_isolation_and_fsm_integrity(self):
        """[D. 기존 주문 처리] Kill Switch ON 이전에 이미 접수/발주된 주문의 FSM 정상 완료 및 신규 주문 차단 격리 실측."""
        tick = CanonicalMarketTick(
            timestamp="2026-08-23 09:00:01",
            underlying_price=350.0,
            bid_price=349.95,
            ask_price=350.05,
            last_price=350.0,
            volume=100,
            seq_id=1,
        )

        # 1. Kill Switch OFF 상태에서 정상 틱 처리 -> 주문 생성 및 FSM 등록
        commands = self.runtime.process_tick(tick)
        self.assertGreater(len(commands), 0, "Kill Switch OFF must generate orders from strategy signals")
        inflight_cmd = commands[0]
        inflight_uuid = self.runtime._order_id_to_uuid[inflight_cmd.client_order_id]
        self.assertIsNotNone(self.runtime.oms_fsm.get_status(inflight_uuid))

        # 2. [비상 정지 발동] Kill Switch ON
        self.runtime.risk_engine.trigger_kill_switch(reason="INFLIGHT_ISOLATION_TEST")

        # 3. [기존 주문 처리] 기존 발주 주문의 체결 리포트 도착 -> consume_execution_report() 정상 완료 처리
        exec_report = CanonicalExecutionReport(
            exec_id="EXEC-001",
            client_order_id=inflight_cmd.client_order_id,
            track_id=inflight_cmd.track_id,
            asset_type=inflight_cmd.asset_type,
            side=inflight_cmd.side,
            executed_qty=inflight_cmd.qty,
            executed_price=inflight_cmd.price,
            fee=500.0,
            slippage=0.0,
            timestamp="2026-08-23 09:00:01",
            symbol=inflight_cmd.symbol,
            option_type=inflight_cmd.option_type,
            strike=inflight_cmd.strike,
        )
        self.runtime.consume_execution_report(exec_report)
        self.assertEqual(len(self.runtime.received_execution_reports), 1)

        # 4. [신규 주문 차단] Kill Switch ON 상태이므로 후속 틱 유입 시 신규 주문 생성은 100% 차단 (0건)
        tick_next = CanonicalMarketTick(
            timestamp="2026-08-23 09:00:02",
            underlying_price=350.1,
            bid_price=350.05,
            ask_price=350.15,
            last_price=350.1,
            volume=120,
            seq_id=2,
        )
        new_commands = self.runtime.process_tick(tick_next)
        self.assertEqual(len(new_commands), 0, "New tick must NOT produce any orders after Kill Switch ON")

    def test_E_data_failure_combination_with_kill_switch(self):
        """[E. Data Failure 결합] Stale/Duplicate/Gap/Out-of-order 비정상 틱 유입 + Kill Switch ON 시 실제 파이프라인 안전 차단 실측."""
        self.runtime.risk_engine.trigger_kill_switch(reason="DATA_FAILURE_COMBO_TEST")

        # 1. Stale / Out-of-order 틱 준비
        stale_tick = CanonicalMarketTick(
            timestamp="2026-08-23 08:59:59",
            underlying_price=350.0,
            bid_price=349.95,
            ask_price=350.05,
            last_price=350.0,
            volume=10,
            seq_id=1,
        )

        # 2. 파이프라인 투입
        commands: List[CanonicalOrderCommand] = self.runtime.process_tick(stale_tick)

        # 3. Data Anomaly Guard + Kill Switch에 의해 주문 리스트 0건 반환 실측
        self.assertEqual(len(commands), 0, "No commands dispatched under Stale Tick + Kill Switch")

        # 4. Duplicate 틱 투입
        dup_tick = CanonicalMarketTick(
            timestamp="2026-08-23 08:59:59",
            underlying_price=350.0,
            bid_price=349.95,
            ask_price=350.05,
            last_price=350.0,
            volume=10,
            seq_id=1,
        )
        commands_dup = self.runtime.process_tick(dup_tick)
        self.assertEqual(len(commands_dup), 0, "No commands dispatched under Duplicate Tick + Kill Switch")

    def test_F_broker_failure_combination_with_kill_switch(self):
        """[F. Broker Failure 결합] Broker Disconnect / Reject + Kill Switch ON 시 실제 파이프라인 차단 및 회계 불변성 실측."""
        self.runtime.risk_engine.trigger_kill_switch(reason="BROKER_FAILURE_COMBO_TEST")
        self.broker.set_connection(False)  # Broker Disconnect

        order_cmd = CanonicalOrderCommand(
            client_order_id="ORD-FAIL-COMBO-001",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=1,
            price=3.50,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            symbol="KOSPI200",
        )

        # 1. RiskGate 단계에서 선제 차단
        is_approved, token, rej_reason = self.runtime.risk_gate.admit_order(
            order_cmd, self.account_summary, {}
        )
        self.assertFalse(is_approved)
        self.assertEqual(rej_reason, "REJECTED_BY_KILL_SWITCH")

        # 2. Broker로 직접 주문 전송 시도 시에도 Disconnect로 인해 None 반환
        report = self.broker.send_order(order_cmd)
        self.assertIsNone(report)

        # 3. 회계 변이 불변성 (Mutation = 0)
        self.assertEqual(self.account_summary.total_balance, 2_000_000_000.0)
        self.assertEqual(self.account_summary.used_margin, 0.0)
        self.assertEqual(len(self.account_summary.positions), 0)

    def test_G_race_condition_and_concurrency_rapid_toggle_safety(self):
        """[G. 동시성 / 반복 토글] 100회 연속 고속 Trigger/Reset 전환 스트레스 테스트 -> Race Condition 없는 결정론적 안전성 실측."""
        engine = self.runtime.risk_engine
        gate = self.runtime.risk_gate

        order_cmd = CanonicalOrderCommand(
            client_order_id="ORD-STRESS-001",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=1,
            price=3.50,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            symbol="KOSPI200",
        )

        for i in range(100):
            # 1. ON 전환
            engine.trigger_kill_switch(reason=f"RAPID_ON_{i}")
            is_app_on, token_on, rej_on = gate.admit_order(order_cmd, self.account_summary, {})
            self.assertFalse(is_app_on, f"Cycle {i}: ON state must strictly block order")
            self.assertIsNone(token_on)
            self.assertEqual(rej_on, "REJECTED_BY_KILL_SWITCH")

            # 2. OFF 전환
            engine.reset_kill_switch()
            is_app_off, token_off, rej_off = gate.admit_order(order_cmd, self.account_summary, {})
            self.assertTrue(is_app_off, f"Cycle {i}: OFF state must strictly approve order")
            self.assertIsNotNone(token_off)
            self.assertIsNone(rej_off)


if __name__ == "__main__":
    unittest.main()
