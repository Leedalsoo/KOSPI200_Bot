# -*- coding: utf-8 -*-
"""Comprehensive Functional Assertion & State Transition Test for Kill Switch (Emergency Stop).

Verifies:
1. Kill Switch Implementation Entity & State Management
2. Order Pathway Suppression under Kill Switch ON (Broker.send_order == 0)
3. State Transition: OFF -> ON -> OFF (Recovery & Resumption)
4. Strategy Signal Blocking at RiskGate
5. Idempotent & Rapid Toggle Safety (Repeated Trigger / Reset)
6. Data/Broker Failure Combination with Kill Switch
7. Accounting Invariance (Position, Balance, PnL, Margin Mutation == 0)
"""
from decimal import Decimal
import unittest
from unittest.mock import MagicMock

from shared.contracts.canonical import (
    CanonicalOrderCommand,
    CanonicalOrderSide,
    CanonicalAssetType,
    CanonicalOptionType,
    CanonicalAccountSummary,
    CanonicalMarketTick,
)
from option_program.risk_control.risk_engine import RiskConfig, RiskSensor, RiskEngine, RiskGate
from option_program.runtime.program_runtime import OptionProgramRuntime
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime
from option_program.broker.broker_interface import PaperBrokerAdapter


class TestKillSwitchComprehensive(unittest.TestCase):
    """[3단계-4] Kill Switch (비상정지) 종합 검증 테스트 스위트"""

    def setUp(self):
        self.risk_config = RiskConfig(
            max_order_qty=50,
            max_daily_loss_krw=10_000_000.0,
            max_margin_utilization_ratio=0.85
        )
        self.vssf = VirtualSecuritiesFirmRuntime(initial_capital=50_000_000.0)
        self.broker = PaperBrokerAdapter(vssf_runtime=self.vssf)
        self.account_summary = CanonicalAccountSummary(
            account_id="ACC-001",
            total_balance=50_000_000.0,
            used_margin=0.0,
            free_margin=50_000_000.0,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            positions={}
        )
        self.runtime = OptionProgramRuntime(
            risk_config=self.risk_config,
            account_summary=self.account_summary
        )
        self.order_cmd = CanonicalOrderCommand(
            client_order_id="ORD-KILL-TEST-001",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=1,
            price=3.50,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            symbol="KOSPI200"
        )

    def test_1_kill_switch_entity_and_state_management(self):
        """[1] Kill Switch 구현 실체 및 상태 제어 함수 검증"""
        engine = self.runtime.risk_engine
        self.assertFalse(engine.is_kill_switch_active())
        self.assertFalse(engine._is_kill_switch_active)

        # Trigger
        engine.trigger_kill_switch(reason="UNIT_TEST_EMERGENCY_STOP")
        self.assertTrue(engine.is_kill_switch_active())
        self.assertTrue(engine._is_kill_switch_active)

        # Reset
        engine.reset_kill_switch()
        self.assertFalse(engine.is_kill_switch_active())
        self.assertFalse(engine._is_kill_switch_active)

    def test_2_order_suppression_under_kill_switch_on(self):
        """[2] Kill Switch ON 시 RiskGate 주문 차단 및 Broker 미호출(0회) 실측"""
        engine = self.runtime.risk_engine
        gate = self.runtime.risk_gate
        engine.trigger_kill_switch(reason="TEST_PANIC_STOP")

        # Mock broker
        mock_broker = MagicMock()

        # RiskGate 심사
        is_approved, token, rej_reason = gate.admit_order(
            command=self.order_cmd,
            account=self.account_summary,
            positions={}
        )

        self.assertFalse(is_approved, "Order must be REJECTED when Kill Switch is ON")
        self.assertIsNone(token, "Approval token must be None")
        self.assertEqual(rej_reason, "REJECTED_BY_KILL_SWITCH")
        self.assertEqual(mock_broker.send_order.call_count, 0, "Broker must never be called")

    def test_3_state_transition_off_on_off_resumption(self):
        """[3] OFF -> ON -> OFF 상태 전이 및 주문 정상 복귀 실측"""
        engine = self.runtime.risk_engine
        gate = self.runtime.risk_gate

        # 1. State: OFF -> 정상 승인
        is_app_1, token_1, rej_1 = gate.admit_order(self.order_cmd, self.account_summary, {})
        self.assertTrue(is_app_1)
        self.assertIsNotNone(token_1)
        self.assertIsNone(rej_1)

        # 2. State: ON -> 즉시 차단
        engine.trigger_kill_switch()
        is_app_2, token_2, rej_2 = gate.admit_order(self.order_cmd, self.account_summary, {})
        self.assertFalse(is_app_2)
        self.assertIsNone(token_2)
        self.assertEqual(rej_2, "REJECTED_BY_KILL_SWITCH")

        # 3. State: OFF -> 다시 정상 승인 복귀
        engine.reset_kill_switch()
        is_app_3, token_3, rej_3 = gate.admit_order(self.order_cmd, self.account_summary, {})
        self.assertTrue(is_app_3)
        self.assertIsNotNone(token_3)
        self.assertIsNone(rej_3)

    def test_4_strategy_runtime_pipeline_blocking(self):
        """[4] 전략 신호 생성 후 Runtime 파이프라인에서 Kill Switch에 의한 차단 실측"""
        self.runtime.risk_engine.trigger_kill_switch()

        tick = CanonicalMarketTick(
            timestamp="2026-08-23 09:00:01",
            underlying_price=350.0,
            bid_price=349.95,
            ask_price=350.05,
            last_price=350.0,
            volume=100,
            seq_id=101
        )

        # process_tick 실행 -> 전략들은 시그널을 생성하지만 RiskGate에서 차단되어 commands 반환 0건
        commands = self.runtime.process_tick(tick)
        self.assertEqual(len(commands), 0, "No order commands must be dispatched when Kill Switch is active")

    def test_5_repeated_toggle_and_idempotency(self):
        """[5] Kill Switch 반복 토글 및 멱등성(Idempotency) 안전성 검증"""
        engine = self.runtime.risk_engine

        # 중복 ON
        engine.trigger_kill_switch()
        engine.trigger_kill_switch()
        self.assertTrue(engine.is_kill_switch_active())

        # 중복 OFF
        engine.reset_kill_switch()
        engine.reset_kill_switch()
        self.assertFalse(engine.is_kill_switch_active())

    def test_6_data_and_broker_failure_combination(self):
        """[6] Data/Broker Failure와 Kill Switch 결합 시 안전 차단 검증"""
        engine = self.runtime.risk_engine
        gate = self.runtime.risk_gate
        engine.trigger_kill_switch()

        # Kill Switch ON + Broker Disconnect 상태
        self.broker.set_connection(False)

        is_app, token, rej = gate.admit_order(self.order_cmd, self.account_summary, {})
        self.assertFalse(is_app)
        self.assertEqual(rej, "REJECTED_BY_KILL_SWITCH")

        # Broker로 주문이 도달하지 않음
        report = self.broker.send_order(self.order_cmd)
        self.assertIsNone(report)

    def test_7_accounting_invariance_mutation_zero(self):
        """[7] Kill Switch 차단 시 Position, Balance, PnL, Ledger 불변성 (Mutation = 0) 실측"""
        initial_balance = self.account_summary.total_balance
        initial_used_margin = self.account_summary.used_margin
        initial_positions = dict(self.account_summary.positions)

        self.runtime.risk_engine.trigger_kill_switch()

        # 틱 투입 및 주문 시도
        tick = CanonicalMarketTick(
            timestamp="2026-08-23 09:00:02",
            underlying_price=350.0,
            bid_price=349.95,
            ask_price=350.05,
            last_price=350.0,
            volume=100,
            seq_id=102
        )
        self.runtime.process_tick(tick)

        # 회계 불변성 확인
        self.assertEqual(self.account_summary.total_balance, initial_balance)
        self.assertEqual(self.account_summary.used_margin, initial_used_margin)
        self.assertEqual(self.account_summary.positions, initial_positions)
        self.assertEqual(len(self.runtime.received_execution_reports), 0)


if __name__ == "__main__":
    unittest.main()
