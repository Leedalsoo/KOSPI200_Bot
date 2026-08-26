"""Risk Expected Position vs Actual Position 일치성 종합 E2E 검증 테스트 스위트.

검증 핵심 불변식:
    Risk Expected Position == Execution 후 Actual Position

검증 영역:
1. LONG 시나리오 (L1: 신규진입, L2: 추가진입, L3: 부분청산, L4: 완전청산, L5: LONG➔SHORT 반전)
2. SHORT 시나리오 (S1: 신규진입, S2: 추가진입, S3: 부분청산, S4: 완전청산, S5: SHORT➔LONG 반전)
3. Risk Position Limit 검증 (R1~R6: 수량 초과 거부 및 청산/감소 주문 정상 승인)
4. Instrument Identity 격리 (A/B 상호 독립성 검증)
"""
import sys
import unittest
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.contracts.canonical import (  # noqa: E402
    CanonicalMarketTick,
    CanonicalOrderCommand,
    CanonicalExecutionReport,
    CanonicalOrderSide,
    CanonicalAssetType,
    CanonicalOptionType,
)
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime  # noqa: E402
from option_program.risk_control.risk_engine import RiskConfig, RiskEngine, RiskGate  # noqa: E402
from option_program.broker.broker_interface import BrokerFactory, BrokerMode  # noqa: E402
from option_program.runtime.program_runtime import OptionProgramRuntime  # noqa: E402


class TestRiskExpectedVsActualPositionE2E(unittest.TestCase):
    """Risk Expected Position ↔ Execution ↔ Actual Position 완전 일치성 E2E 검증."""

    def setUp(self):
        self.initial_capital = 5_000_000_000.0  # 50억원
        self.vssf = VirtualSecuritiesFirmRuntime(initial_capital=self.initial_capital)
        self.broker = BrokerFactory.create_broker(mode=BrokerMode.PAPER, vssf_runtime=self.vssf)
        self.risk_config = RiskConfig(
            max_order_qty=100,
            max_daily_loss_krw=500_000_000.0,
            max_margin_utilization_ratio=0.85,
            max_position_per_instrument=100,
        )
        self.op_runtime = OptionProgramRuntime(
            risk_config=self.risk_config,
            account_summary=self.vssf.get_account_snapshot(),
        )

        self.base_tick = CanonicalMarketTick(
            timestamp="2026-08-23 09:00:00.000",
            underlying_price=2.5,
            bid_price=2.45,
            ask_price=2.55,
            last_price=2.5,
            volume=1000,
            seq_id=1,
        )
        self.vssf.process_market_data(self.base_tick)
        self.op_runtime.update_account_summary(self.vssf.get_account_snapshot())


        self.inst_a_key = "KOSPI200_OPTION_2026-09_CALL_350.0"
        self.inst_b_key = "KOSPI200_OPTION_2026-09_CALL_360.0"


    # =========================================================================
    # 1. LONG 시나리오 (L1 ~ L5)
    # =========================================================================

    def test_L1_long_new_entry(self):
        """[TEST L1] LONG 신규진입: FLAT -> BUY 10 -> Expected: LONG 10 == Actual: LONG 10."""
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-L1", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            qty=10, price=2.5, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )

        # 1. Risk Expected Position 계산
        expected = self.op_runtime.risk_gate.engine.calculate_expected_position(
            cmd, self.vssf.account.get_positions()
        )
        self.assertEqual(expected["instrument_key"], self.inst_a_key)
        self.assertEqual(expected["side"], "BUY")
        self.assertEqual(expected["qty"], 10)

        # 2. RiskGate 심사 및 승인
        is_app, token, _ = self.op_runtime.risk_gate.admit_order(
            cmd, self.op_runtime.account_summary, self.vssf.account.get_positions()
        )
        self.assertTrue(is_app)

        # 3. 체결 및 Actual Position 반영
        report = self.broker.send_order(cmd)
        self.assertIsNotNone(report)
        self.assertEqual(report.executed_qty, 10)

        # 4. 검증: Expected Position == Actual Position
        actual_pos = self.vssf.account.get_positions().get(self.inst_a_key, {})
        self.assertEqual(actual_pos.get("side"), expected["side"])
        self.assertEqual(actual_pos.get("qty"), expected["qty"])

    def test_L2_long_additional_entry(self):
        """[TEST L2] LONG 추가진입: LONG 10 -> BUY 5 -> Expected: LONG 15 == Actual: LONG 15."""
        # 초기 LONG 10 체결
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-INIT-L2", client_order_id="ORD-INIT", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=10, executed_price=2.5, fee=100.0, slippage=0.0,
            timestamp="2026-08-23 09:00:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))

        cmd = CanonicalOrderCommand(
            client_order_id="ORD-L2", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            qty=5, price=2.5, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )

        expected = self.op_runtime.risk_gate.engine.calculate_expected_position(
            cmd, self.vssf.account.get_positions()
        )
        self.assertEqual(expected["side"], "BUY")
        self.assertEqual(expected["qty"], 15)

        is_app, _, _ = self.op_runtime.risk_gate.admit_order(
            cmd, self.op_runtime.account_summary, self.vssf.account.get_positions()
        )
        self.assertTrue(is_app)

        report = self.broker.send_order(cmd)
        self.assertIsNotNone(report)

        actual_pos = self.vssf.account.get_positions().get(self.inst_a_key, {})
        self.assertEqual(actual_pos.get("side"), expected["side"])
        self.assertEqual(actual_pos.get("qty"), expected["qty"])

    def test_L3_long_partial_close(self):
        """[TEST L3] LONG 부분청산: LONG 15 -> SELL 5 -> Expected: LONG 10 == Actual: LONG 10."""
        # 초기 LONG 15
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-INIT-L3", client_order_id="ORD-INIT", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=15, executed_price=2.5, fee=150.0, slippage=0.0,
            timestamp="2026-08-23 09:00:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))

        cmd = CanonicalOrderCommand(
            client_order_id="ORD-L3", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.SELL,
            qty=5, price=2.5, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )

        expected = self.op_runtime.risk_gate.engine.calculate_expected_position(
            cmd, self.vssf.account.get_positions()
        )
        self.assertEqual(expected["side"], "BUY")
        self.assertEqual(expected["qty"], 10)

        is_app, _, _ = self.op_runtime.risk_gate.admit_order(
            cmd, self.op_runtime.account_summary, self.vssf.account.get_positions()
        )
        self.assertTrue(is_app)

        report = self.broker.send_order(cmd)
        self.assertIsNotNone(report)

        actual_pos = self.vssf.account.get_positions().get(self.inst_a_key, {})
        self.assertEqual(actual_pos.get("side"), expected["side"])
        self.assertEqual(actual_pos.get("qty"), expected["qty"])

    def test_L4_long_full_close(self):
        """[TEST L4] LONG 완전청산: LONG 10 -> SELL 10 -> Expected: FLAT 0 == Actual: FLAT 0."""
        # 초기 LONG 10
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-INIT-L4", client_order_id="ORD-INIT", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=10, executed_price=2.5, fee=100.0, slippage=0.0,
            timestamp="2026-08-23 09:00:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))

        cmd = CanonicalOrderCommand(
            client_order_id="ORD-L4", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.SELL,
            qty=10, price=2.5, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )

        expected = self.op_runtime.risk_gate.engine.calculate_expected_position(
            cmd, self.vssf.account.get_positions()
        )
        self.assertEqual(expected["side"], "FLAT")
        self.assertEqual(expected["qty"], 0)

        is_app, _, _ = self.op_runtime.risk_gate.admit_order(
            cmd, self.op_runtime.account_summary, self.vssf.account.get_positions()
        )
        self.assertTrue(is_app)

        report = self.broker.send_order(cmd)
        self.assertIsNotNone(report)

        actual_pos = self.vssf.account.get_positions().get(self.inst_a_key, {})
        actual_qty = actual_pos.get("qty", 0)
        self.assertEqual(actual_qty, expected["qty"])

    def test_L5_long_to_short_reversal(self):
        """[TEST L5] LONG -> SHORT 반전: LONG 10 -> SELL 15 -> Expected: SHORT 5 == Actual: SHORT 5."""
        # 초기 LONG 10
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-INIT-L5", client_order_id="ORD-INIT", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=10, executed_price=2.5, fee=100.0, slippage=0.0,
            timestamp="2026-08-23 09:00:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))

        cmd = CanonicalOrderCommand(
            client_order_id="ORD-L5", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.SELL,
            qty=15, price=2.5, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )

        expected = self.op_runtime.risk_gate.engine.calculate_expected_position(
            cmd, self.vssf.account.get_positions()
        )
        self.assertEqual(expected["side"], "SELL")
        self.assertEqual(expected["qty"], 5)

        is_app, _, _ = self.op_runtime.risk_gate.admit_order(
            cmd, self.op_runtime.account_summary, self.vssf.account.get_positions()
        )
        self.assertTrue(is_app)

        report = self.broker.send_order(cmd)
        self.assertIsNotNone(report)

        actual_pos = self.vssf.account.get_positions().get(self.inst_a_key, {})
        self.assertEqual(actual_pos.get("side"), expected["side"])
        self.assertEqual(actual_pos.get("qty"), expected["qty"])

    # =========================================================================
    # 2. SHORT 시나리오 (S1 ~ S5)
    # =========================================================================

    def test_S1_short_new_entry(self):
        """[TEST S1] SHORT 신규진입: FLAT -> SELL 10 -> Expected: SHORT 10 == Actual: SHORT 10."""
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-S1", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.SELL,
            qty=10, price=2.5, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )

        expected = self.op_runtime.risk_gate.engine.calculate_expected_position(
            cmd, self.vssf.account.get_positions()
        )
        self.assertEqual(expected["side"], "SELL")
        self.assertEqual(expected["qty"], 10)

        is_app, _, _ = self.op_runtime.risk_gate.admit_order(
            cmd, self.op_runtime.account_summary, self.vssf.account.get_positions()
        )
        self.assertTrue(is_app)

        report = self.broker.send_order(cmd)
        self.assertIsNotNone(report)

        actual_pos = self.vssf.account.get_positions().get(self.inst_a_key, {})
        self.assertEqual(actual_pos.get("side"), expected["side"])
        self.assertEqual(actual_pos.get("qty"), expected["qty"])

    def test_S2_short_additional_entry(self):
        """[TEST S2] SHORT 추가진입: SHORT 10 -> SELL 5 -> Expected: SHORT 15 == Actual: SHORT 15."""
        # 초기 SHORT 10
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-INIT-S2", client_order_id="ORD-INIT", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.SELL,
            executed_qty=10, executed_price=2.5, fee=100.0, slippage=0.0,
            timestamp="2026-08-23 09:00:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))

        cmd = CanonicalOrderCommand(
            client_order_id="ORD-S2", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.SELL,
            qty=5, price=2.5, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )

        expected = self.op_runtime.risk_gate.engine.calculate_expected_position(
            cmd, self.vssf.account.get_positions()
        )
        self.assertEqual(expected["side"], "SELL")
        self.assertEqual(expected["qty"], 15)

        is_app, _, _ = self.op_runtime.risk_gate.admit_order(
            cmd, self.op_runtime.account_summary, self.vssf.account.get_positions()
        )
        self.assertTrue(is_app)

        report = self.broker.send_order(cmd)
        self.assertIsNotNone(report)

        actual_pos = self.vssf.account.get_positions().get(self.inst_a_key, {})
        self.assertEqual(actual_pos.get("side"), expected["side"])
        self.assertEqual(actual_pos.get("qty"), expected["qty"])

    def test_S3_short_partial_close(self):
        """[TEST S3] SHORT 부분청산: SHORT 15 -> BUY 5 -> Expected: SHORT 10 == Actual: SHORT 10."""
        # 초기 SHORT 15
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-INIT-S3", client_order_id="ORD-INIT", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.SELL,
            executed_qty=15, executed_price=2.5, fee=150.0, slippage=0.0,
            timestamp="2026-08-23 09:00:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))

        cmd = CanonicalOrderCommand(
            client_order_id="ORD-S3", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            qty=5, price=2.5, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )

        expected = self.op_runtime.risk_gate.engine.calculate_expected_position(
            cmd, self.vssf.account.get_positions()
        )
        self.assertEqual(expected["side"], "SELL")
        self.assertEqual(expected["qty"], 10)

        is_app, _, _ = self.op_runtime.risk_gate.admit_order(
            cmd, self.op_runtime.account_summary, self.vssf.account.get_positions()
        )
        self.assertTrue(is_app)

        report = self.broker.send_order(cmd)
        self.assertIsNotNone(report)

        actual_pos = self.vssf.account.get_positions().get(self.inst_a_key, {})
        self.assertEqual(actual_pos.get("side"), expected["side"])
        self.assertEqual(actual_pos.get("qty"), expected["qty"])

    def test_S4_short_full_close(self):
        """[TEST S4] SHORT 완전청산: SHORT 10 -> BUY 10 -> Expected: FLAT 0 == Actual: FLAT 0."""
        # 초기 SHORT 10
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-INIT-S4", client_order_id="ORD-INIT", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.SELL,
            executed_qty=10, executed_price=2.5, fee=100.0, slippage=0.0,
            timestamp="2026-08-23 09:00:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))

        cmd = CanonicalOrderCommand(
            client_order_id="ORD-S4", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            qty=10, price=2.5, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )

        expected = self.op_runtime.risk_gate.engine.calculate_expected_position(
            cmd, self.vssf.account.get_positions()
        )
        self.assertEqual(expected["side"], "FLAT")
        self.assertEqual(expected["qty"], 0)

        is_app, _, _ = self.op_runtime.risk_gate.admit_order(
            cmd, self.op_runtime.account_summary, self.vssf.account.get_positions()
        )
        self.assertTrue(is_app)

        report = self.broker.send_order(cmd)
        self.assertIsNotNone(report)

        actual_pos = self.vssf.account.get_positions().get(self.inst_a_key, {})
        actual_qty = actual_pos.get("qty", 0)
        self.assertEqual(actual_qty, expected["qty"])

    def test_S5_short_to_long_reversal(self):
        """[TEST S5] SHORT -> LONG 반전: SHORT 10 -> BUY 15 -> Expected: LONG 5 == Actual: LONG 5."""
        # 초기 SHORT 10
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-INIT-S5", client_order_id="ORD-INIT", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.SELL,
            executed_qty=10, executed_price=2.5, fee=100.0, slippage=0.0,
            timestamp="2026-08-23 09:00:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))

        cmd = CanonicalOrderCommand(
            client_order_id="ORD-S5", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            qty=15, price=2.5, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )

        expected = self.op_runtime.risk_gate.engine.calculate_expected_position(
            cmd, self.vssf.account.get_positions()
        )
        self.assertEqual(expected["side"], "BUY")
        self.assertEqual(expected["qty"], 5)

        is_app, _, _ = self.op_runtime.risk_gate.admit_order(
            cmd, self.op_runtime.account_summary, self.vssf.account.get_positions()
        )
        self.assertTrue(is_app)

        report = self.broker.send_order(cmd)
        self.assertIsNotNone(report)

        actual_pos = self.vssf.account.get_positions().get(self.inst_a_key, {})
        self.assertEqual(actual_pos.get("side"), expected["side"])
        self.assertEqual(actual_pos.get("qty"), expected["qty"])

    # =========================================================================
    # 3. Risk Position Limit 검증 (R1 ~ R6)
    # =========================================================================

    def test_R1_long_overflow_reject(self):
        """[TEST R1] LONG 95 + BUY 6 -> Expected LONG 101 > 100 -> Risk REJECT."""
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-R1", client_order_id="ORD-R1-INIT", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=95, executed_price=2.5, fee=950.0, slippage=0.0,
            timestamp="2026-08-23 09:00:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))

        cmd = CanonicalOrderCommand(
            client_order_id="ORD-R1-BUY6", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            qty=6, price=2.5, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )

        is_app, _, rej = self.op_runtime.risk_gate.admit_order(
            cmd, self.op_runtime.account_summary, self.vssf.account.get_positions()
        )
        self.assertFalse(is_app)
        self.assertIn("EXCEEDED_INSTRUMENT_LIMIT", str(rej))

        # Actual Position은 LONG 95 유지
        actual_pos = self.vssf.account.get_positions()[self.inst_a_key]
        self.assertEqual(actual_pos["qty"], 95)
        self.assertEqual(actual_pos["side"], "BUY")

    def test_R2_long_close_order_approved(self):
        """[TEST R2] LONG 95 + SELL 5 -> Expected LONG 90 -> Risk PASS."""
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-R2", client_order_id="ORD-R2-INIT", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=95, executed_price=2.5, fee=950.0, slippage=0.0,
            timestamp="2026-08-23 09:00:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))

        cmd = CanonicalOrderCommand(
            client_order_id="ORD-R2-SELL5", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.SELL,
            qty=5, price=2.5, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )

        is_app, _, rej = self.op_runtime.risk_gate.admit_order(
            cmd, self.op_runtime.account_summary, self.vssf.account.get_positions()
        )
        self.assertTrue(is_app, f"청산 주문은 정상 승인되어야 함 (Rejection: {rej})")

    def test_R3_long_full_close_approved(self):
        """[TEST R3] LONG 95 + SELL 95 -> Expected FLAT 0 -> Risk PASS."""
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-R3", client_order_id="ORD-R3-INIT", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=95, executed_price=2.5, fee=950.0, slippage=0.0,
            timestamp="2026-08-23 09:00:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))

        cmd = CanonicalOrderCommand(
            client_order_id="ORD-R3-SELL95", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.SELL,
            qty=95, price=2.5, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )

        is_app, _, rej = self.op_runtime.risk_gate.admit_order(
            cmd, self.op_runtime.account_summary, self.vssf.account.get_positions()
        )
        self.assertTrue(is_app, f"전량 청산 주문은 정상 승인되어야 함 (Rejection: {rej})")

    def test_R4_short_overflow_reject(self):
        """[TEST R4] SHORT 95 + SELL 6 -> Expected SHORT 101 > 100 -> Risk REJECT."""
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-R4", client_order_id="ORD-R4-INIT", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.SELL,
            executed_qty=95, executed_price=2.5, fee=950.0, slippage=0.0,
            timestamp="2026-08-23 09:00:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))
        self.op_runtime.update_account_summary(self.vssf.get_account_snapshot())

        cmd = CanonicalOrderCommand(
            client_order_id="ORD-R4-SELL6", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.SELL,
            qty=6, price=2.5, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )

        is_app, _, rej = self.op_runtime.risk_gate.admit_order(
            cmd, self.op_runtime.account_summary, self.vssf.account.get_positions()
        )
        self.assertFalse(is_app)
        self.assertIn("EXCEEDED_INSTRUMENT_LIMIT", str(rej))

        # Actual Position은 SHORT 95 유지
        actual_pos = self.vssf.account.get_positions()[self.inst_a_key]
        self.assertEqual(actual_pos["qty"], 95)
        self.assertEqual(actual_pos["side"], "SELL")

    def test_R5_short_close_order_approved(self):
        """[TEST R5] SHORT 95 + BUY 5 -> Expected SHORT 90 -> Risk PASS."""
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-R5", client_order_id="ORD-R5-INIT", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.SELL,
            executed_qty=95, executed_price=2.5, fee=950.0, slippage=0.0,
            timestamp="2026-08-23 09:00:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))
        self.op_runtime.update_account_summary(self.vssf.get_account_snapshot())

        cmd = CanonicalOrderCommand(
            client_order_id="ORD-R5-BUY5", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            qty=5, price=2.5, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )

        is_app, _, rej = self.op_runtime.risk_gate.admit_order(
            cmd, self.op_runtime.account_summary, self.vssf.account.get_positions()
        )
        self.assertTrue(is_app, f"숏 청산 주문은 정상 승인되어야 함 (Rejection: {rej})")

    def test_R6_short_full_close_approved(self):
        """[TEST R6] SHORT 95 + BUY 95 -> Expected FLAT 0 -> Risk PASS."""
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-R6", client_order_id="ORD-R6-INIT", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.SELL,
            executed_qty=95, executed_price=2.5, fee=950.0, slippage=0.0,
            timestamp="2026-08-23 09:00:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))
        self.op_runtime.update_account_summary(self.vssf.get_account_snapshot())

        cmd = CanonicalOrderCommand(
            client_order_id="ORD-R6-BUY95", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            qty=95, price=2.5, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )

        is_app, _, rej = self.op_runtime.risk_gate.admit_order(
            cmd, self.op_runtime.account_summary, self.vssf.account.get_positions()
        )
        self.assertTrue(is_app, f"숏 전량 청산 주문은 정상 승인되어야 함 (Rejection: {rej})")


    # =========================================================================
    # 4. Instrument Identity 격리 검증 (I1)
    # =========================================================================

    def test_I1_instrument_isolation_no_cross_interference(self):
        """[TEST I1] Instrument A에 LONG 95가 존재할 때, Instrument B에 BUY 100 -> A 간섭 없이 승인 및 독립 유지."""
        # A에 LONG 95 체결
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-I1-A", client_order_id="ORD-A-95", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=95, executed_price=2.5, fee=950.0, slippage=0.0,
            timestamp="2026-08-23 09:00:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))

        # B 신규 BUY 100 주문
        cmd_b = CanonicalOrderCommand(
            client_order_id="ORD-I1-B", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            qty=100, price=2.5, option_type=CanonicalOptionType.CALL,
            strike=360.0, expiry="2026-09"
        )

        # 1. B의 Expected Position 계산
        expected_b = self.op_runtime.risk_gate.engine.calculate_expected_position(
            cmd_b, self.vssf.account.get_positions()
        )
        self.assertEqual(expected_b["instrument_key"], self.inst_b_key)
        self.assertEqual(expected_b["qty"], 100)
        self.assertEqual(expected_b["side"], "BUY")

        # 2. RiskGate 심사 (A의 95계약 때문에 거부되지 않고 정상 승인)
        is_app, _, rej = self.op_runtime.risk_gate.admit_order(
            cmd_b, self.op_runtime.account_summary, self.vssf.account.get_positions()
        )
        self.assertTrue(is_app, f"B의 주문은 A의 간섭 없이 승인되어야 함 (Rejection: {rej})")

        # 3. B 체결
        report_b = self.broker.send_order(cmd_b)
        self.assertIsNotNone(report_b)

        # 4. 검증: A와 B가 독립된 포지션으로 공존
        positions = self.vssf.account.get_positions()
        self.assertIn(self.inst_a_key, positions)
        self.assertIn(self.inst_b_key, positions)
        self.assertEqual(positions[self.inst_a_key]["qty"], 95)
        self.assertEqual(positions[self.inst_a_key]["side"], "BUY")
        self.assertEqual(positions[self.inst_b_key]["qty"], expected_b["qty"])
        self.assertEqual(positions[self.inst_b_key]["side"], expected_b["side"])


if __name__ == "__main__":
    unittest.main()
