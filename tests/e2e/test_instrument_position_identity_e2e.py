"""옵션 종목별 Instrument Identity 정규화 및 Risk-Position 연결 E2E 테스트 스위트.

핵심 원칙:
"하나의 실제 옵션 Instrument = 하나의 독립적인 Position"
식별 기준: symbol, asset_type, expiry, option_type, strike

12대 필수 검증 시나리오:
- TEST 1: CALL 350 매수 ➔ CALL 350 Position 생성
- TEST 2: CALL 360 매수 ➔ CALL 350과 별도의 Position 생성
- TEST 3: PUT 350 매수 ➔ CALL 350 / CALL 360과 별도의 Position 생성
- TEST 4: 동일 strike + option_type + expiry 추가 체결 ➔ 기존 동일 Position에 수량 누적
- TEST 5: 다른 expiry 체결 ➔ 별도 Position 생성
- TEST 6: 동일 Instrument 추가 매수 ➔ 수량 및 가중평균단가 정확히 갱신
- TEST 7: 동일 Instrument 청산 ➔ 해당 Instrument Position만 감소/청산
- TEST 8: Instrument A Position이 95일 때 ➔ A 추가 6계약은 Risk REJECT
- TEST 9: Instrument A Position이 95일 때 ➔ Instrument B 추가 100계약은 A 때문에 REJECT되지 않음
- TEST 10: Position 변경 후 다음 Risk 계산 ➔ 변경된 Actual Position 정확히 조회
- TEST 11: 동일 Instrument ExecutionReport 중복 전달 ➔ Position 중복 반영 금지
- TEST 12: Order/Execution 데이터의 Instrument Identity가 Position까지 손실 없이 전달됨
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
    build_instrument_key,
)
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime  # noqa: E402
from option_program.risk_control.risk_engine import RiskConfig, RiskEngine, RiskGate  # noqa: E402
from option_program.broker.broker_interface import BrokerFactory, BrokerMode  # noqa: E402
from option_program.runtime.program_runtime import OptionProgramRuntime  # noqa: E402


class TestInstrumentPositionIdentityE2E(unittest.TestCase):
    """옵션 종목별 Instrument Identity 정규화 E2E 테스트 스위트."""

    def setUp(self):
        self.initial_capital = 5_000_000_000.0
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
            underlying_price=350.0,
            bid_price=349.9,
            ask_price=350.1,
            last_price=350.0,
            volume=1000,
            seq_id=1,
        )
        self.vssf.process_market_data(self.base_tick)
        self.op_runtime.update_account_summary(self.vssf.get_account_snapshot())

    def test_01_call_350_creates_distinct_position(self):
        """[TEST 1] CALL 350 매수 -> CALL 350 전용 Position 생성."""
        rep = CanonicalExecutionReport(
            exec_id="EXEC-T1-001",
            client_order_id="ORD-T1-001",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            executed_qty=5,
            executed_price=350.0,
            fee=5000.0,
            slippage=0.0,
            timestamp="2026-08-23 09:00:00",
            symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
        )
        self.vssf.account.apply_execution(rep)

        positions = self.vssf.account.get_positions()
        expected_key = "KOSPI200_OPTION_2026-09_CALL_350.0"
        self.assertIn(expected_key, positions)
        self.assertEqual(positions[expected_key]["qty"], 5)
        self.assertEqual(positions[expected_key]["side"], "BUY")

    def test_02_call_360_creates_separate_position_from_call_350(self):
        """[TEST 2] CALL 360 매수 -> CALL 350과 분리된 별도 Position 생성."""
        # 1. CALL 350 체결
        rep_350 = CanonicalExecutionReport(
            exec_id="EXEC-T2-001",
            client_order_id="ORD-T2-001",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            executed_qty=10,
            executed_price=350.0,
            fee=10000.0,
            slippage=0.0,
            timestamp="2026-08-23 09:00:00",
            symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
        )
        self.vssf.account.apply_execution(rep_350)

        # 2. CALL 360 체결
        rep_360 = CanonicalExecutionReport(
            exec_id="EXEC-T2-002",
            client_order_id="ORD-T2-002",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            executed_qty=20,
            executed_price=360.0,
            fee=20000.0,
            slippage=0.0,
            timestamp="2026-08-23 09:01:00",
            symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL,
            strike=360.0,
            expiry="2026-09",
        )
        self.vssf.account.apply_execution(rep_360)

        positions = self.vssf.account.get_positions()
        key_350 = "KOSPI200_OPTION_2026-09_CALL_350.0"
        key_360 = "KOSPI200_OPTION_2026-09_CALL_360.0"

        # 검증: 두 포지션이 합쳐지지 않고 각각 독립 존재
        self.assertIn(key_350, positions)
        self.assertIn(key_360, positions)
        self.assertEqual(positions[key_350]["qty"], 10)
        self.assertEqual(positions[key_360]["qty"], 20)

    def test_03_put_350_creates_separate_position_from_call_options(self):
        """[TEST 3] PUT 350 매수 -> CALL 350 / CALL 360과 분리된 별도 Position 생성."""
        # 1. CALL 350 체결
        rep_call = CanonicalExecutionReport(
            exec_id="EXEC-T3-001",
            client_order_id="ORD-T3-001",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            executed_qty=5,
            executed_price=350.0,
            fee=5000.0,
            slippage=0.0,
            timestamp="2026-08-23 09:00:00",
            symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
        )
        self.vssf.account.apply_execution(rep_call)

        # 2. PUT 350 체결
        rep_put = CanonicalExecutionReport(
            exec_id="EXEC-T3-002",
            client_order_id="ORD-T3-002",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            executed_qty=7,
            executed_price=350.0,
            fee=7000.0,
            slippage=0.0,
            timestamp="2026-08-23 09:01:00",
            symbol="KOSPI200",
            option_type=CanonicalOptionType.PUT,
            strike=350.0,
            expiry="2026-09",
        )
        self.vssf.account.apply_execution(rep_put)

        positions = self.vssf.account.get_positions()
        key_call = "KOSPI200_OPTION_2026-09_CALL_350.0"
        key_put = "KOSPI200_OPTION_2026-09_PUT_350.0"

        self.assertIn(key_call, positions)
        self.assertIn(key_put, positions)
        self.assertEqual(positions[key_call]["qty"], 5)
        self.assertEqual(positions[key_put]["qty"], 7)

    def test_04_same_instrument_accumulates_quantity(self):
        """[TEST 4] 동일 strike + option_type + expiry 추가 체결 -> 기존 동일 Position에 수량 누적."""
        key = "KOSPI200_OPTION_2026-09_CALL_350.0"

        # 1차: 4계약
        rep1 = CanonicalExecutionReport(
            exec_id="EXEC-T4-001",
            client_order_id="ORD-T4-001",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            executed_qty=4,
            executed_price=350.0,
            fee=4000.0,
            slippage=0.0,
            timestamp="2026-08-23 09:00:00",
            symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
        )
        self.vssf.account.apply_execution(rep1)

        # 2차: 동일 종목 6계약
        rep2 = CanonicalExecutionReport(
            exec_id="EXEC-T4-002",
            client_order_id="ORD-T4-002",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            executed_qty=6,
            executed_price=350.0,
            fee=6000.0,
            slippage=0.0,
            timestamp="2026-08-23 09:02:00",
            symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
        )
        self.vssf.account.apply_execution(rep2)

        positions = self.vssf.account.get_positions()
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[key]["qty"], 10)

    def test_05_different_expiry_creates_separate_position(self):
        """[TEST 5] 다른 expiry 체결 -> 별도 Position 생성."""
        # 2026-09 만기 CALL 350
        rep_sep = CanonicalExecutionReport(
            exec_id="EXEC-T5-001",
            client_order_id="ORD-T5-001",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            executed_qty=5,
            executed_price=350.0,
            fee=5000.0,
            slippage=0.0,
            timestamp="2026-08-23 09:00:00",
            symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
        )
        self.vssf.account.apply_execution(rep_sep)

        # 2026-12 만기 CALL 350
        rep_dec = CanonicalExecutionReport(
            exec_id="EXEC-T5-002",
            client_order_id="ORD-T5-002",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            executed_qty=8,
            executed_price=352.0,
            fee=8000.0,
            slippage=0.0,
            timestamp="2026-08-23 09:01:00",
            symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-12",
        )
        self.vssf.account.apply_execution(rep_dec)

        positions = self.vssf.account.get_positions()
        key_sep = "KOSPI200_OPTION_2026-09_CALL_350.0"
        key_dec = "KOSPI200_OPTION_2026-12_CALL_350.0"

        self.assertIn(key_sep, positions)
        self.assertIn(key_dec, positions)
        self.assertEqual(positions[key_sep]["qty"], 5)
        self.assertEqual(positions[key_dec]["qty"], 8)

    def test_06_same_instrument_weighted_average_price_update(self):
        """[TEST 6] 동일 Instrument 추가 매수 -> 수량 및 가중평균단가 정확히 갱신."""
        key = "KOSPI200_OPTION_2026-09_CALL_350.0"

        # 1차: 2계약 @ 350.0
        rep1 = CanonicalExecutionReport(
            exec_id="EXEC-T6-001",
            client_order_id="ORD-T6-001",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            executed_qty=2,
            executed_price=350.0,
            fee=2000.0,
            slippage=0.0,
            timestamp="2026-08-23 09:00:00",
            symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
        )
        self.vssf.account.apply_execution(rep1)

        # 2차: 3계약 @ 355.0
        rep2 = CanonicalExecutionReport(
            exec_id="EXEC-T6-002",
            client_order_id="ORD-T6-002",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            executed_qty=3,
            executed_price=355.0,
            fee=3000.0,
            slippage=0.0,
            timestamp="2026-08-23 09:01:00",
            symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
        )
        self.vssf.account.apply_execution(rep2)

        positions = self.vssf.account.get_positions()
        self.assertEqual(positions[key]["qty"], 5)
        # (2*350 + 3*355)/5 = 1765/5 = 353.0
        self.assertEqual(positions[key]["avg_price"], 353.0)

    def test_07_same_instrument_position_close_isolation(self):
        """[TEST 7] 동일 Instrument 청산 -> 해당 Instrument Position만 감소/청산되고 타 Instrument 영향 없음."""
        key_350 = "KOSPI200_OPTION_2026-09_CALL_350.0"
        key_360 = "KOSPI200_OPTION_2026-09_CALL_360.0"

        # 1. CALL 350 4계약 매수
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-T7-001", client_order_id="ORD-1", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=4, executed_price=350.0, fee=4000.0, slippage=0.0,
            timestamp="2026-08-23 09:00:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))

        # 2. CALL 360 8계약 매수
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-T7-002", client_order_id="ORD-2", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=8, executed_price=360.0, fee=8000.0, slippage=0.0,
            timestamp="2026-08-23 09:01:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=360.0, expiry="2026-09"
        ))

        # 3. CALL 350 전량 4계약 매도 청산
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-T7-003", client_order_id="ORD-3", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.SELL,
            executed_qty=4, executed_price=353.0, fee=4000.0, slippage=0.0,
            timestamp="2026-08-23 09:05:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))

        positions = self.vssf.account.get_positions()
        # CALL 350은 청산되어 수량 0 (제거)
        self.assertNotIn(key_350, positions)
        # CALL 360은 온전히 8계약 유지
        self.assertIn(key_360, positions)
        self.assertEqual(positions[key_360]["qty"], 8)

    def test_08_instrument_a_limit_rejection_at_95_qty(self):
        """[TEST 8] Instrument A Position이 95일 때 -> A 추가 6계약은 Risk REJECT (95 + 6 = 101 > 100)."""
        key_a = "KOSPI200_OPTION_2026-09_CALL_350.0"

        # Instrument A 95계약 체결 (옵션 프리미엄 2.5)
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-T8-001", client_order_id="ORD-A-1", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=95, executed_price=2.5, fee=950.0, slippage=0.0,
            timestamp="2026-08-23 09:00:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))

        self.op_runtime.update_account_summary(self.vssf.get_account_snapshot())

        # Instrument A 추가 6계약 주문
        cmd_a_overflow = CanonicalOrderCommand(
            client_order_id="ORD-A-OVERFLOW",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=6,
            price=2.5,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
        )

        is_approved, token, rej = self.op_runtime.risk_gate.admit_order(
            command=cmd_a_overflow,
            account=self.op_runtime.account_summary,
            positions=self.op_runtime.account_summary.positions,
        )

        self.assertFalse(is_approved)
        self.assertIn("EXCEEDED_INSTRUMENT_LIMIT", str(rej))

    def test_09_instrument_b_not_rejected_due_to_instrument_a_position(self):
        """[TEST 9] Instrument A Position이 95일 때 -> Instrument B 추가 100계약은 A 때문에 REJECT되지 않음."""
        # Instrument A (CALL 350) 95계약 체결
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-T9-001", client_order_id="ORD-A-1", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=95, executed_price=2.5, fee=950.0, slippage=0.0,
            timestamp="2026-08-23 09:00:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))

        self.op_runtime.update_account_summary(self.vssf.get_account_snapshot())

        # Instrument B (CALL 360) 100계약 신규 주문 시도 (B의 포지션은 0이므로 0 + 100 <= 100 허용)
        cmd_b = CanonicalOrderCommand(
            client_order_id="ORD-B-100",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=100,
            price=2.5,
            option_type=CanonicalOptionType.CALL,
            strike=360.0,
            expiry="2026-09",
        )

        is_approved, token, rej = self.op_runtime.risk_gate.admit_order(
            command=cmd_b,
            account=self.op_runtime.account_summary,
            positions=self.op_runtime.account_summary.positions,
        )

        # Instrument A와 독립적으로 심사되어 승인됨
        self.assertTrue(is_approved, f"Instrument B 주문은 승인되어야 함 (Rejection: {rej})")
        self.assertIsNotNone(token)

    def test_10_next_risk_evaluation_reads_updated_specific_instrument_position(self):
        """[TEST 10] Position 변경 후 다음 Risk 계산 시 변경된 Actual Position 정확히 조회."""
        # PUT 350 90계약 체결
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-T10-001", client_order_id="ORD-P-1", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=90, executed_price=2.5, fee=900.0, slippage=0.0,
            timestamp="2026-08-23 09:00:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.PUT, strike=350.0, expiry="2026-09"
        ))

        self.op_runtime.update_account_summary(self.vssf.get_account_snapshot())

        # PUT 350 10계약 주문 -> 90 + 10 = 100 <= 100 (승인)
        cmd_ok = CanonicalOrderCommand(
            client_order_id="ORD-P-OK", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            qty=10, price=2.5, option_type=CanonicalOptionType.PUT,
            strike=350.0, expiry="2026-09"
        )
        ok_approved, _, _ = self.op_runtime.risk_gate.admit_order(
            cmd_ok, self.op_runtime.account_summary, self.op_runtime.account_summary.positions
        )
        self.assertTrue(ok_approved)

        # PUT 350 11계약 주문 -> 90 + 11 = 101 > 100 (거부)
        cmd_reject = CanonicalOrderCommand(
            client_order_id="ORD-P-REJ", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            qty=11, price=2.5, option_type=CanonicalOptionType.PUT,
            strike=350.0, expiry="2026-09"
        )
        rej_approved, _, rej_reason = self.op_runtime.risk_gate.admit_order(
            cmd_reject, self.op_runtime.account_summary, self.op_runtime.account_summary.positions
        )
        self.assertFalse(rej_approved)
        self.assertIn("EXCEEDED_INSTRUMENT_LIMIT", str(rej_reason))


    def test_11_duplicate_execution_report_idempotency_for_same_instrument(self):
        """[TEST 11] 동일 Instrument ExecutionReport 중복 전달 -> Position 중복 반영 금지 (멱등성)."""
        key = "KOSPI200_OPTION_2026-09_CALL_350.0"
        rep_dup = CanonicalExecutionReport(
            exec_id="EXEC-T11-DUP",
            client_order_id="ORD-T11-001",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            executed_qty=5,
            executed_price=350.0,
            fee=5000.0,
            slippage=0.0,
            timestamp="2026-08-23 09:00:00",
            symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
        )

        # 1차 반영
        self.vssf.account.apply_execution(rep_dup)
        self.assertEqual(self.vssf.account.get_positions()[key]["qty"], 5)

        # 2차 중복 리포트 투입
        self.vssf.account.apply_execution(rep_dup)
        # 10이 아니라 5 유지 확인
        self.assertEqual(self.vssf.account.get_positions()[key]["qty"], 5)

    def test_12_instrument_identity_lossless_round_trip(self):
        """[TEST 12] Order Command ➔ ExecutionReport ➔ Position 전체 경로에서 Instrument Identity 무손실 보존 확인."""
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-T12-FULL",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=3,
            price=355.0,
            option_type=CanonicalOptionType.PUT,
            strike=355.0,
            expiry="2026-10",
        )

        expected_key = "KOSPI200_OPTION_2026-10_PUT_355.0"
        self.assertEqual(cmd.get_instrument_key(), expected_key)

        # Broker 체결 발주
        report = self.broker.send_order(cmd)
        self.assertIsNotNone(report)
        self.assertEqual(report.get_instrument_key(), expected_key)

        # VSSF 포지션 반영
        positions = self.vssf.account.get_positions()
        self.assertIn(expected_key, positions)
        self.assertEqual(positions[expected_key]["qty"], 3)


if __name__ == "__main__":
    unittest.main()
