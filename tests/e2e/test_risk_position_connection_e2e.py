"""Risk와 실제 Position의 연결성 종합 E2E 검증 테스트 스위트.

검증 핵심 원칙:
"Order intent ≠ Execution ≠ Actual Position"

검증 경로:
Market Tick ➔ Strategy Signal ➔ RiskGate Pre-Trade Admission ➔ Order Command ➔ Broker Execution ➔ ExecutionReport ➔ VSSF Account & Actual Position Mutation ➔ Next Risk State Reference

11대 필수 검증 시나리오:
- TEST 1: Risk 승인 ➔ Order 생성 ➔ Broker 체결 ➔ ExecutionReport ➔ VSSF Actual Position 증가
- TEST 2: Risk 거부 ➔ Order 미실행 ➔ Actual Position 변화 없음
- TEST 3: Broker Reject ➔ Actual Position 변화 없음
- TEST 4: 부분 체결 (Partial Fill) ➔ 실제 체결 수량만 Position에 반영
- TEST 5: 기존 Position 보유 상태에서 추가 매수/매도 ➔ 평균단가/수량/노출량 정확 갱신
- TEST 6: Position 청산 ➔ 실제 Position 수량 감소 및 완전 청산 시 0
- TEST 7: Position 반전 ➔ LONG 10 ➔ SELL 15 ➔ LONG 0, SHORT 5
- TEST 8: 동일 ExecutionReport 중복 전달 ➔ Position 중복 반영 방지 (Idempotent)
- TEST 9: ExecutionReport 없이 Order만 생성 ➔ Actual Position 변화 없음
- TEST 10: Position 변경 후 다음 Risk 계산 시 변경된 Actual Position 정확히 참조
- TEST 11: Margin / Exposure 계산이 Actual Position과 100% 일치
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


class TestRiskPositionConnectionE2E(unittest.TestCase):
    """Risk ↔ Execution ↔ Actual Position 연결성 종합 검증 테스트 스위트."""

    def setUp(self):
        self.initial_capital = 500_000_000.0
        self.vssf = VirtualSecuritiesFirmRuntime(initial_capital=self.initial_capital)
        self.broker = BrokerFactory.create_broker(mode=BrokerMode.PAPER, vssf_runtime=self.vssf)
        self.risk_config = RiskConfig(
            max_order_qty=50,
            max_daily_loss_krw=50_000_000.0,
            max_margin_utilization_ratio=0.85,
            max_position_per_instrument=100,
        )
        self.op_runtime = OptionProgramRuntime(
            risk_config=self.risk_config,
            account_summary=self.vssf.get_account_snapshot(),
        )


        # 초기 시세 설정
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

    def test_01_risk_approval_to_actual_position_increase(self):
        """[TEST 1] Risk 승인 -> Order -> Broker 체결 -> ExecutionReport -> VSSF Actual Position 증가."""
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-TEST-001",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=2,
            price=350.0,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
        )

        # 1. RiskGate 심사 (가용증거금 충분 -> 승인)
        is_approved, token, rej = self.op_runtime.risk_gate.admit_order(
            command=cmd,
            account=self.op_runtime.account_summary,
            positions=self.op_runtime.account_summary.positions,
        )
        self.assertTrue(is_approved)
        self.assertIsNotNone(token)
        self.assertIsNone(rej)

        # 2. Broker 체결 실행
        report = self.broker.send_order(cmd)
        self.assertIsNotNone(report)
        self.assertEqual(report.executed_qty, 2)

        # 3. VSSF Actual Position 증가 확인
        positions = self.vssf.account.get_positions()
        inst_key = report.get_instrument_key()
        self.assertIn(inst_key, positions)
        self.assertEqual(positions[inst_key]["qty"], 2)
        self.assertEqual(positions[inst_key]["side"], "BUY")
        self.assertEqual(positions[inst_key]["avg_price"], report.executed_price)



    def test_02_risk_rejection_no_position_change(self):
        """[TEST 2] Risk 거부 (1회 최대 수량 50 초과) -> Order 미실행 -> Actual Position 변화 없음."""
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-TEST-002",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=60,  # max_order_qty=50 초과
            price=350.0,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
        )

        # 1. RiskGate 심사 (수량 초과 -> 거부)
        is_approved, token, rej = self.op_runtime.risk_gate.admit_order(
            command=cmd,
            account=self.op_runtime.account_summary,
            positions=self.op_runtime.account_summary.positions,
        )
        self.assertFalse(is_approved)
        self.assertIsNone(token)
        self.assertIn("EXCEEDED_MAX_ORDER_QTY", str(rej))

        # 2. 거부된 주문은 Broker로 라우팅되지 않음 -> Position 변화 없음
        positions = self.vssf.account.get_positions()
        self.assertEqual(len(positions), 0)

    def test_03_broker_reject_no_position_change(self):
        """[TEST 3] Broker Reject (예: Broker 통신 끊김) -> Actual Position 변화 없음."""
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-TEST-003",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=1,
            price=350.0,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
        )

        # Broker 연결 끊김 설정
        self.broker.set_connection(False)
        report = self.broker.send_order(cmd)
        self.assertIsNone(report)

        # Position 변화 없음 확인
        positions = self.vssf.account.get_positions()
        self.assertEqual(len(positions), 0)

    def test_04_partial_fill_exact_position_reflection(self):
        """[TEST 4] 부분 체결 -> 실제 체결 수량만 Position에 반영."""
        rep = CanonicalExecutionReport(
            exec_id="EXEC-PARTIAL-001",
            client_order_id="ORD-PARTIAL-001",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            executed_qty=3,  # 주문 5개 중 3개만 부분 체결
            executed_price=350.0,
            fee=3000.0,
            slippage=0.0,
            timestamp="2026-08-23 09:00:00",
        )

        # VSSF 계좌에 부분 체결 리포트 반영
        self.vssf.account.apply_execution(rep)

        positions = self.vssf.account.get_positions()
        self.assertEqual(positions["KOSPI200_OPTION"]["qty"], 3)

    def test_05_additional_position_accumulation_and_avg_price(self):
        """[TEST 5] 기존 Position 보유 상태에서 추가 매수 -> 수량 및 가중평균단가 정확 갱신."""
        # 1차 매수: 2계약 @ 350.0
        rep1 = CanonicalExecutionReport(
            exec_id="EXEC-ACC-001",
            client_order_id="ORD-ACC-001",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            executed_qty=2,
            executed_price=350.0,
            fee=2000.0,
            slippage=0.0,
            timestamp="2026-08-23 09:00:00",
        )
        self.vssf.account.apply_execution(rep1)

        # 2차 추가 매수: 3계약 @ 355.0
        rep2 = CanonicalExecutionReport(
            exec_id="EXEC-ACC-002",
            client_order_id="ORD-ACC-002",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            executed_qty=3,
            executed_price=355.0,
            fee=3000.0,
            slippage=0.0,
            timestamp="2026-08-23 09:01:00",
        )
        self.vssf.account.apply_execution(rep2)

        positions = self.vssf.account.get_positions()
        # 총 수량: 2 + 3 = 5
        self.assertEqual(positions["KOSPI200_OPTION"]["qty"], 5)
        # 가중평균단가: (2*350 + 3*355) / 5 = (700 + 1065) / 5 = 1765 / 5 = 353.0
        self.assertEqual(positions["KOSPI200_OPTION"]["avg_price"], 353.0)

    def test_06_position_close_and_reduction_to_zero(self):
        """[TEST 6] Position 청산 -> 실제 Position 수량 감소 및 완전 청산 시 0 (제거)."""
        # 1. 4계약 매수
        rep_buy = CanonicalExecutionReport(
            exec_id="EXEC-CLS-001",
            client_order_id="ORD-CLS-001",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            executed_qty=4,
            executed_price=350.0,
            fee=4000.0,
            slippage=0.0,
            timestamp="2026-08-23 09:00:00",
        )
        self.vssf.account.apply_execution(rep_buy)
        self.assertEqual(self.vssf.account.get_positions()["KOSPI200_OPTION"]["qty"], 4)

        # 2. 4계약 전량 매도 청산
        rep_sell = CanonicalExecutionReport(
            exec_id="EXEC-CLS-002",
            client_order_id="ORD-CLS-002",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.SELL,
            executed_qty=4,
            executed_price=352.0,
            fee=4000.0,
            slippage=0.0,
            timestamp="2026-08-23 09:02:00",
        )
        self.vssf.account.apply_execution(rep_sell)

        # 완전 청산 시 positions에서 제거되거나 수량 0
        positions = self.vssf.account.get_positions()
        qty = positions.get("KOSPI200_OPTION", {}).get("qty", 0)
        self.assertEqual(qty, 0)
        # 실현 손익 발생 확인: (352.0 - 350.0) * 4 * 250000 = 2.0 * 1,000,000 = +2,000,000 KRW
        self.assertEqual(self.vssf.account.realized_pnl, 2_000_000.0)

    def test_07_position_reversal_long_to_short(self):
        """[TEST 7] Position 반전: LONG 10 -> SELL 15 -> LONG 0, SHORT 5."""
        # 1. LONG 10계약 매수
        rep_long = CanonicalExecutionReport(
            exec_id="EXEC-REV-001",
            client_order_id="ORD-REV-001",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            executed_qty=10,
            executed_price=350.0,
            fee=10000.0,
            slippage=0.0,
            timestamp="2026-08-23 09:00:00",
        )
        self.vssf.account.apply_execution(rep_long)
        self.assertEqual(self.vssf.account.get_positions()["KOSPI200_OPTION"]["qty"], 10)
        self.assertEqual(self.vssf.account.get_positions()["KOSPI200_OPTION"]["side"], "BUY")

        # 2. SELL 15계약 매도 (10 청산 + 5 신규 숏)
        rep_rev = CanonicalExecutionReport(
            exec_id="EXEC-REV-002",
            client_order_id="ORD-REV-002",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.SELL,
            executed_qty=15,
            executed_price=351.0,
            fee=15000.0,
            slippage=0.0,
            timestamp="2026-08-23 09:05:00",
        )
        self.vssf.account.apply_execution(rep_rev)

        # 결과: SHORT 5계약 @ 351.0
        positions = self.vssf.account.get_positions()
        self.assertEqual(positions["KOSPI200_OPTION"]["qty"], 5)
        self.assertEqual(positions["KOSPI200_OPTION"]["side"], "SELL")
        self.assertEqual(positions["KOSPI200_OPTION"]["avg_price"], 351.0)

    def test_08_duplicate_execution_report_idempotency(self):
        """[TEST 8] 동일 ExecutionReport 중복 전달 -> Position 중복 반영되지 않음 (Idempotent)."""
        rep = CanonicalExecutionReport(
            exec_id="EXEC-DUP-001",
            client_order_id="ORD-DUP-001",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            executed_qty=2,
            executed_price=350.0,
            fee=2000.0,
            slippage=0.0,
            timestamp="2026-08-23 09:00:00",
        )

        # 1차 수신 반영
        self.vssf.account.apply_execution(rep)
        self.assertEqual(self.vssf.account.get_positions()["KOSPI200_OPTION"]["qty"], 2)

        # 2차 동일 리포트 중복 수신
        self.vssf.account.apply_execution(rep)
        # 여전히 수량은 2여야 함 (4가 되지 않음)
        self.assertEqual(self.vssf.account.get_positions()["KOSPI200_OPTION"]["qty"], 2)

    def test_09_order_only_without_execution_no_position_change(self):
        """[TEST 9] ExecutionReport 없이 Order Command만 생성 -> Actual Position 변화 없음."""
        _ = CanonicalOrderCommand(
            client_order_id="ORD-INTENT-ONLY",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=5,
            price=350.0,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
        )

        # 주문 객체만 생성되고 체결되지 않음 -> Position 없음
        positions = self.vssf.account.get_positions()
        self.assertEqual(len(positions), 0)

    def test_10_next_risk_evaluation_references_updated_actual_position(self):
        """[TEST 10] Position이 실제로 변경된 후 다음 Risk 계산 시 변경된 Actual Position 정확히 참조."""
        # 1. 95계약 체결하여 보유 (종목당 최대한도: 100)
        rep = CanonicalExecutionReport(
            exec_id="EXEC-RISK-REF-001",
            client_order_id="ORD-RISK-REF-001",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            executed_qty=95,
            executed_price=2.5,
            fee=950.0,
            slippage=0.0,
            timestamp="2026-08-23 09:00:00",
        )
        self.vssf.account.apply_execution(rep)

        # 최신 계좌 스냅샷 동기화
        latest_summary = self.vssf.get_account_snapshot()
        self.op_runtime.update_account_summary(latest_summary)

        # 2. 추가 10계약 매수 주문 시도 (95 + 10 = 105 > 100 한도 초과)
        cmd_overflow = CanonicalOrderCommand(
            client_order_id="ORD-OVERFLOW",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=10,
            price=2.5,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
        )


        is_approved, token, rej = self.op_runtime.risk_gate.admit_order(
            command=cmd_overflow,
            account=self.op_runtime.account_summary,
            positions=self.op_runtime.account_summary.positions,
        )

        # RiskGate가 실제 포지션(95)을 읽어서 100 초과로 정확히 거부해야 함!
        self.assertFalse(is_approved)
        self.assertIn("EXCEEDED_INSTRUMENT_LIMIT", str(rej))

    def test_11_margin_and_exposure_match_actual_positions(self):
        """[TEST 11] Margin / Exposure 계산이 Actual Position과 100% 일치."""
        # 2계약 매수 체결
        rep = CanonicalExecutionReport(
            exec_id="EXEC-MARGIN-001",
            client_order_id="ORD-MARGIN-001",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            executed_qty=2,
            executed_price=350.0,
            fee=2000.0,
            slippage=0.0,
            timestamp="2026-08-23 09:00:00",
        )
        self.vssf.account.apply_execution(rep)

        # 마켓 시세 업데이트
        self.vssf.process_market_data(self.base_tick)
        snap = self.vssf.get_account_snapshot()

        # VSSF의 사용 증거금과 포지션 기반 계산이 정확히 일치하는지 확인
        expected_used_margin = self.vssf.account.margin_engine.calculate_used_margin(self.vssf.account.positions)
        self.assertEqual(snap.used_margin, round(expected_used_margin, 2))
        expected_free = max(0.0, round(snap.total_balance - snap.used_margin, 2))
        self.assertEqual(snap.free_margin, expected_free)



if __name__ == "__main__":
    unittest.main()
