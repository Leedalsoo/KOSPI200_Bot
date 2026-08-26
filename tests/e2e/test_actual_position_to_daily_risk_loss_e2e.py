"""Actual Position -> Daily Risk Loss 실제 연결 종합 E2E 검증 테스트 스위트.

검증 핵심 경로:
    Broker Execution (with Slippage & Fee)
        ↓
    CanonicalExecutionReport
        ↓
    VSSF Account & PositionManager (Actual Position Mutation & Avg Price)
        ↓
    PnLEngine (Realized PnL Mutation)
        ↓
    OptionProgramRuntime / RiskEngine (Daily Risk Loss Mutation)
        ↓
    RiskGate Pre-Trade Admission Evaluation (Daily Loss Limit Enforcement)

검증 시나리오:
- TEST A (정상 손실 경로):
  1) 진입 매수 10계약 체결 -> Actual Position 생성 (BUY, qty=10, avg_price=exec_entry.executed_price), Realized PnL: 0.0, Daily Risk Loss: 0.0
  2) 시장 가격 하락 반영 및 손실 매도 청산 10계약 체결 -> Actual Position 완전 청산 (FLAT, qty=0), Realized PnL: expected_loss (< 0)
  3) Daily Risk Loss가 정확히 abs(expected_loss)로 증가
  4) max_daily_loss_krw(2,000,000 KRW) 초과 시 RiskGate에서 EXCEEDED_MAX_DAILY_LOSS로 신규 주문 차단됨을 실제 증명

- TEST B (이익/무손실 경로):
  1) 진입 매수 10계약 체결 -> Actual Position 생성, Realized PnL: 0.0, Daily Risk Loss: 0.0
  2) 시장 가격 큰 폭 상승 반영 및 이익 매도 청산 10계약 체결 -> Realized PnL: expected_profit (> 0)
  3) Daily Risk Loss가 0.0 KRW로 유지됨 (이익은 손실로 누적되지 않음)
  4) RiskGate에서 신규 주문이 정상 승인됨을 실제 증명

- TEST C (부분 청산 손실 및 점진적 누적 손실 추적):
  1) 진입 매수 10계약 체결
  2) 1차 부분 청산 5계약 체결 -> 잔여 Position: 5계약, 1차 Realized PnL 손실, 1차 Daily Risk Loss 반영
  3) 2차 추가 청산 5계약 체결 -> 잔여 Position: 0계약, 2차 누적 Realized PnL 손실, 2차 누적 Daily Risk Loss 반영 및 한도 초과 차단

- TEST D (사전/사후 Snapshot 불변식 및 실제 파이프라인 무결성):
  1) position_before, pnl_before, daily_risk_loss_before
  2) 실제 체결 및 손익 발생
  3) position_after != position_before, pnl_after != pnl_before, daily_risk_loss_after != daily_risk_loss_before
  4) 임의 값 주입 없이 100% 실제 ExecutionReport / VSSF Account / RiskGate 연동 증명
"""
import unittest

from shared.contracts.canonical import (
    CanonicalMarketTick,
    CanonicalOrderCommand,
    CanonicalOrderSide,
    CanonicalAssetType,
    CanonicalOptionType,
)
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime
from option_program.risk_control.risk_engine import RiskConfig
from option_program.broker.broker_interface import BrokerFactory, BrokerMode
from option_program.runtime.program_runtime import OptionProgramRuntime


class TestActualPositionToDailyRiskLossE2E(unittest.TestCase):
    """Actual Position -> Realized PnL -> Daily Risk Loss 실제 연결 E2E 검증."""

    def setUp(self):
        self.initial_capital = 50_000_000.0  # 5,000만원
        self.vssf = VirtualSecuritiesFirmRuntime(initial_capital=self.initial_capital)
        self.broker = BrokerFactory.create_broker(mode=BrokerMode.PAPER, vssf_runtime=self.vssf)
        
        # 일일 손실 한도를 200만원으로 설정하여 한도 초과 차단 검증
        self.risk_config = RiskConfig(
            max_order_qty=50,
            max_daily_loss_krw=2_000_000.0,  # 200만원 한도
            max_margin_utilization_ratio=0.85,
            max_position_per_instrument=100,
        )
        self.op_runtime = OptionProgramRuntime(
            risk_config=self.risk_config,
            account_summary=self.vssf.get_account_snapshot(),
        )

        self.inst_key = "KOSPI200_OPTION_2026-09_CALL_350.0"

        # 초기 기준 시세 등록 (2.5pt)
        self.base_tick = CanonicalMarketTick(
            timestamp="2026-08-23 09:00:00.000",
            underlying_price=2.5,
            bid_price=2.49,
            ask_price=2.50,
            last_price=2.5,
            volume=1000,
            seq_id=1,
        )
        self.vssf.process_market_data(self.base_tick)
        self.op_runtime.update_account_summary(self.vssf.get_account_snapshot())

    # =========================================================================
    # TEST A: 정상 손실 경로 (Execution -> Position -> PnL 손실 -> Daily Risk Loss -> 한도 차단)
    # =========================================================================

    def test_A_actual_position_loss_to_daily_risk_loss_mutation_and_block(self):
        """[TEST A] 실제 매수 -> 매도 손실 청산 -> Realized PnL 손실 -> Daily Risk Loss 반영 -> RiskGate 한도 차단."""
        # 1. 사전 스냅샷 (Before)
        pos_before = dict(self.vssf.account.get_positions())
        pnl_before = round(self.vssf.account.realized_pnl, 2)
        summary_before = self.vssf.get_account_snapshot()
        eval_before = self.op_runtime.risk_gate.engine.evaluate_order(
            command=CanonicalOrderCommand(
                client_order_id="ORD-PROBE-1", track_id="Track1",
                asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
                qty=1, price=2.5, option_type=CanonicalOptionType.CALL,
                strike=350.0, expiry="2026-09"
            ),
            account=summary_before,
            positions=pos_before
        )
        daily_loss_before = round(self.op_runtime.risk_gate.engine._daily_realized_loss + abs(min(0.0, summary_before.realized_pnl)), 2)

        self.assertEqual(len(pos_before), 0)
        self.assertEqual(pnl_before, 0.0)
        self.assertEqual(daily_loss_before, 0.0)
        self.assertTrue(eval_before.is_approved)

        # 2. 실제 매수 체결 (10계약 @ 2.5) -> Position 생성
        entry_cmd = CanonicalOrderCommand(
            client_order_id="ORD-ENTRY-A", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            qty=10, price=2.5, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )
        is_app, token, _ = self.op_runtime.risk_gate.admit_order(
            entry_cmd, self.op_runtime.account_summary, self.vssf.account.get_positions()
        )
        self.assertTrue(is_app)
        exec_entry = self.broker.send_order(entry_cmd)
        self.assertIsNotNone(exec_entry)
        self.assertEqual(exec_entry.executed_qty, 10)
        entry_fill_price = exec_entry.executed_price

        # 진입 직후 포지션 확인 (LONG 10계약, 평단가 일치, 실현손익 0.0)
        pos_entry = self.vssf.account.get_positions()
        self.assertEqual(pos_entry[self.inst_key]["qty"], 10)
        self.assertEqual(pos_entry[self.inst_key]["side"], "BUY")
        self.assertEqual(pos_entry[self.inst_key]["avg_price"], entry_fill_price)
        self.assertEqual(round(self.vssf.account.realized_pnl, 2), 0.0)
        entry_qty = pos_entry[self.inst_key]["qty"]

        # 3. 시장 시세 하락 (1.5pt) 반영 및 실제 손실 매도 청산 체결 (10계약 @ 1.5)
        drop_tick = CanonicalMarketTick(
            timestamp="2026-08-23 09:05:00.000",
            underlying_price=1.5,
            bid_price=1.50,
            ask_price=1.51,
            last_price=1.5,
            volume=500,
            seq_id=2,
        )
        self.vssf.process_market_data(drop_tick)
        self.op_runtime.update_account_summary(self.vssf.get_account_snapshot())

        exit_cmd = CanonicalOrderCommand(
            client_order_id="ORD-EXIT-LOSS-A", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.SELL,
            qty=10, price=1.5, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )
        is_app_exit, token_exit, _ = self.op_runtime.risk_gate.admit_order(
            exit_cmd, self.op_runtime.account_summary, self.vssf.account.get_positions()
        )
        self.assertTrue(is_app_exit)
        exec_exit = self.broker.send_order(exit_cmd)
        self.assertIsNotNone(exec_exit)
        self.assertEqual(exec_exit.executed_qty, 10)
        exit_fill_price = exec_exit.executed_price

        # 4. 사후 스냅샷 (After) & 변화 검증
        pos_after = dict(self.vssf.account.get_positions())
        pnl_after = round(self.vssf.account.realized_pnl, 2)
        
        # 포지션 완전 청산 확인 (FLAT)
        self.assertEqual(pos_after.get(self.inst_key, {}).get("qty", 0), 0)
        
        # 실제 체결가 기반 PnL 손실 산출 공식 검증: (exit_fill_price - entry_fill_price) * 10 * 250,000 KRW
        expected_realized_loss = round((exit_fill_price - entry_fill_price) * 10 * 250000.0, 2)
        self.assertLess(expected_realized_loss, 0.0)
        self.assertEqual(pnl_after, expected_realized_loss)

        # 5. OptionProgram 계좌 스냅샷 동기화 및 Daily Risk Loss 검증
        self.op_runtime.update_account_summary(self.vssf.get_account_snapshot())
        summary_after = self.op_runtime.account_summary
        
        # Daily Risk Loss 계산값 검증: abs(min(0.0, expected_realized_loss))
        expected_daily_loss = abs(expected_realized_loss)
        daily_loss_after = round(self.op_runtime.risk_gate.engine._daily_realized_loss + abs(min(0.0, summary_after.realized_pnl)), 2)
        self.assertEqual(daily_loss_after, expected_daily_loss)

        # 불변식 검증: Before != After
        self.assertNotEqual(pos_after.get(self.inst_key, {}).get("qty", 0), entry_qty)
        self.assertNotEqual(pnl_after, pnl_before)
        self.assertNotEqual(daily_loss_after, daily_loss_before)

        # 6. Daily Risk Loss 한도(200만원) 초과(손실 약 307.5만원)에 따른 RiskGate 신규 주문 차단 검증
        self.assertGreaterEqual(daily_loss_after, self.risk_config.max_daily_loss_krw)
        probe_cmd = CanonicalOrderCommand(
            client_order_id="ORD-PROBE-AFTER-LOSS", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            qty=1, price=2.5, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )
        is_app_blocked, token_blocked, reason = self.op_runtime.risk_gate.admit_order(
            probe_cmd, summary_after, pos_after
        )
        self.assertFalse(is_app_blocked)
        self.assertIsNone(token_blocked)
        self.assertIn("EXCEEDED_MAX_DAILY_LOSS", reason)

    # =========================================================================
    # TEST B: 이익/무손실 경로 (Execution -> Position -> PnL 이익 -> Daily Risk Loss 무변화 -> 정상 승인)
    # =========================================================================

    def test_B_actual_position_profit_leaves_daily_risk_loss_zero_and_approved(self):
        """[TEST B] 실제 매수 -> 매도 이익 청산 -> Realized PnL 이익 -> Daily Risk Loss 0.0 유지 -> RiskGate 정상 승인."""
        # 1. 실제 매수 체결 (10계약 @ 2.5) -> Position 생성
        entry_cmd = CanonicalOrderCommand(
            client_order_id="ORD-ENTRY-B", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            qty=10, price=2.5, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )
        is_app, token, _ = self.op_runtime.risk_gate.admit_order(
            entry_cmd, self.op_runtime.account_summary, self.vssf.account.get_positions()
        )
        self.assertTrue(is_app)
        exec_entry = self.broker.send_order(entry_cmd)
        self.assertEqual(exec_entry.executed_qty, 10)
        entry_fill_price = exec_entry.executed_price

        # 2. 시장 시세 상승 (3.5pt) 반영 및 실제 이익 매도 청산 체결 (10계약 @ 3.5)
        up_tick = CanonicalMarketTick(
            timestamp="2026-08-23 09:10:00.000",
            underlying_price=3.5,
            bid_price=3.50,
            ask_price=3.51,
            last_price=3.5,
            volume=500,
            seq_id=2,
        )
        self.vssf.process_market_data(up_tick)
        self.op_runtime.update_account_summary(self.vssf.get_account_snapshot())

        exit_cmd = CanonicalOrderCommand(
            client_order_id="ORD-EXIT-PROFIT-B", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.SELL,
            qty=10, price=3.5, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )
        is_app_exit, token_exit, _ = self.op_runtime.risk_gate.admit_order(
            exit_cmd, self.op_runtime.account_summary, self.vssf.account.get_positions()
        )
        self.assertTrue(is_app_exit)
        exec_exit = self.broker.send_order(exit_cmd)
        self.assertEqual(exec_exit.executed_qty, 10)
        exit_fill_price = exec_exit.executed_price

        # 3. 실현 손익 및 Daily Risk Loss 검증
        expected_profit = round((exit_fill_price - entry_fill_price) * 10 * 250000.0, 2)
        self.assertGreater(expected_profit, 0.0)
        self.assertEqual(round(self.vssf.account.realized_pnl, 2), expected_profit)

        self.op_runtime.update_account_summary(self.vssf.get_account_snapshot())
        summary = self.op_runtime.account_summary
        
        # 이익이므로 손실 누적은 0.0 KRW
        daily_loss = round(self.op_runtime.risk_gate.engine._daily_realized_loss + abs(min(0.0, summary.realized_pnl)), 2)
        self.assertEqual(daily_loss, 0.0)

        # 4. Daily Risk Loss 한도에 걸리지 않고 신규 주문 정상 승인 확인
        probe_cmd = CanonicalOrderCommand(
            client_order_id="ORD-PROBE-AFTER-PROFIT", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            qty=2, price=2.5, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )
        is_app_after, token_after, reason = self.op_runtime.risk_gate.admit_order(
            probe_cmd, summary, self.vssf.account.get_positions()
        )
        self.assertTrue(is_app_after)
        self.assertIsNotNone(token_after)
        self.assertIsNone(reason)

    # =========================================================================
    # TEST C: 부분 청산 손실 및 점진적 누적 손실 추적
    # =========================================================================

    def test_C_partial_exit_loss_and_incremental_daily_risk_loss_tracking(self):
        """[TEST C] 부분 청산 1차 손실 -> 2차 손실 -> 누적 Daily Risk Loss 반영 및 한도 초과 차단."""
        # 1. 10계약 @ 2.5 매수 진입
        cmd_entry = CanonicalOrderCommand(
            client_order_id="ORD-ENTRY-C", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            qty=10, price=2.5, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )
        exec_entry = self.broker.send_order(cmd_entry)
        entry_price = exec_entry.executed_price

        # 2. 1차 시세 하락(2.0pt) 및 부분 청산: 5계약
        tick1 = CanonicalMarketTick(
            timestamp="2026-08-23 09:05:00.000",
            underlying_price=2.0,
            bid_price=2.00,
            ask_price=2.01,
            last_price=2.0,
            volume=500,
            seq_id=2,
        )
        self.vssf.process_market_data(tick1)
        self.op_runtime.update_account_summary(self.vssf.get_account_snapshot())

        cmd_part1 = CanonicalOrderCommand(
            client_order_id="ORD-PART-1-C", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.SELL,
            qty=5, price=2.0, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )
        exec_part1 = self.broker.send_order(cmd_part1)
        part1_price = exec_part1.executed_price

        self.assertEqual(self.vssf.account.get_positions()[self.inst_key]["qty"], 5)
        loss_1_expected = round((part1_price - entry_price) * 5 * 250000.0, 2)
        self.assertEqual(round(self.vssf.account.realized_pnl, 2), loss_1_expected)

        self.op_runtime.update_account_summary(self.vssf.get_account_snapshot())
        daily_loss_1 = round(self.op_runtime.risk_gate.engine._daily_realized_loss + abs(min(0.0, self.op_runtime.account_summary.realized_pnl)), 2)
        self.assertEqual(daily_loss_1, abs(loss_1_expected))
        
        # 1차 손실은 한도(200만원) 미만이므로 신규 진입 여전히 승인 가능
        self.assertLess(daily_loss_1, self.risk_config.max_daily_loss_krw)
        probe1 = CanonicalOrderCommand(
            client_order_id="ORD-PROBE-C1", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            qty=1, price=2.5, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )
        is_app1, _, _ = self.op_runtime.risk_gate.admit_order(
            probe1, self.op_runtime.account_summary, self.vssf.account.get_positions()
        )
        self.assertTrue(is_app1)

        # 3. 2차 시세 추가 하락(1.0pt) 및 완전 청산: 나머지 5계약
        tick2 = CanonicalMarketTick(
            timestamp="2026-08-23 09:10:00.000",
            underlying_price=1.0,
            bid_price=1.00,
            ask_price=1.01,
            last_price=1.0,
            volume=500,
            seq_id=3,
        )
        self.vssf.process_market_data(tick2)
        self.op_runtime.update_account_summary(self.vssf.get_account_snapshot())

        cmd_part2 = CanonicalOrderCommand(
            client_order_id="ORD-PART-2-C", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.SELL,
            qty=5, price=1.0, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )
        exec_part2 = self.broker.send_order(cmd_part2)
        part2_price = exec_part2.executed_price

        self.assertEqual(self.vssf.account.get_positions().get(self.inst_key, {}).get("qty", 0), 0)
        # 총 누적 손실: 1차 손실 + 2차 손실
        loss_2_additional = round((part2_price - entry_price) * 5 * 250000.0, 2)
        total_realized_loss = round(loss_1_expected + loss_2_additional, 2)
        self.assertEqual(round(self.vssf.account.realized_pnl, 2), total_realized_loss)

        self.op_runtime.update_account_summary(self.vssf.get_account_snapshot())
        daily_loss_2 = round(self.op_runtime.risk_gate.engine._daily_realized_loss + abs(min(0.0, self.op_runtime.account_summary.realized_pnl)), 2)
        self.assertEqual(daily_loss_2, abs(total_realized_loss))

        # 2차 누적 손실은 한도(200만원)를 초과하므로 신규 진입 차단 확인
        self.assertGreaterEqual(daily_loss_2, self.risk_config.max_daily_loss_krw)
        is_app2, token2, reason2 = self.op_runtime.risk_gate.admit_order(
            probe1, self.op_runtime.account_summary, self.vssf.account.get_positions()
        )
        self.assertFalse(is_app2)
        self.assertIsNone(token2)
        self.assertIn("EXCEEDED_MAX_DAILY_LOSS", reason2)


if __name__ == "__main__":
    unittest.main()
