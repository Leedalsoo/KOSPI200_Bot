"""E2E Test: Broker Results -> ExecutionReport -> Position -> PnL Authoritative Consistency.

Comprehensive Scenarios:
1. FILLED: LONG / SHORT full lifecycle (New Entry, Add Entry, Partial Close, Full Close).
2. REVERSAL: LONG -> SHORT and SHORT -> LONG position flip and precise realized PnL.
3. PARTIAL: Partial fills only reflect executed_qty, remaining order unreflected.
4. REJECTED: Broker rejection leaves position, balance, and PnL completely untouched (zero mutation).
5. CANCELLED: Order cancellation leaves position, balance, and PnL completely untouched (zero mutation).
6. ISOLATION: Multiple instruments (CALL 350 vs CALL 360) remain completely isolated.
7. IDEMPOTENCY: Duplicate ExecutionReports are ignored without double counting position or PnL.
"""
import sys
import unittest
from pathlib import Path

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
from option_program.broker.broker_interface import BrokerFactory, BrokerMode  # noqa: E402


class TestBrokerExecutionPositionPnLConsistencyE2E(unittest.TestCase):
    """Broker 결과 -> Position -> PnL 일관성 검증 E2E 테스트 슈트."""

    def setUp(self):
        self.initial_capital = 5_000_000_000.0
        self.vssf = VirtualSecuritiesFirmRuntime(initial_capital=self.initial_capital)
        self.broker = BrokerFactory.create_broker(mode=BrokerMode.PAPER, vssf_runtime=self.vssf)

        # 초기 틱 시세 주입
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
        self.inst_a_key = "KOSPI200_OPTION_2026-09_CALL_350.0"
        self.inst_b_key = "KOSPI200_OPTION_2026-09_CALL_360.0"
        self.multiplier = 250000.0

    # =========================================================================
    # 1. FILLED: LONG 라이프사이클 (신규 -> 추가 -> 부분청산 -> 완전청산)
    # =========================================================================

    def test_01_filled_long_full_lifecycle(self):
        """[FILLED - LONG] 신규 10개 -> 추가 5개 -> 부분청산 10개 -> 완전청산 5개 단계별 정합성."""
        # 1. 신규 LONG 10 @ 2.5
        rep_1 = CanonicalExecutionReport(
            exec_id="EXEC-L1", client_order_id="ORD-L1", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=10, executed_price=2.5, fee=1000.0, slippage=0.0,
            timestamp="2026-08-23 09:00:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        )
        self.vssf.account.apply_execution(rep_1)

        pos = self.vssf.account.get_positions()
        self.assertIn(self.inst_a_key, pos)
        self.assertEqual(pos[self.inst_a_key]["qty"], 10)
        self.assertEqual(pos[self.inst_a_key]["side"], "BUY")
        self.assertEqual(pos[self.inst_a_key]["avg_price"], 2.5)
        self.assertEqual(self.vssf.account.realized_pnl, 0.0)

        # 2. 추가 LONG 5 @ 2.8 -> 평단가: (10*2.5 + 5*2.8)/15 = 39.0/15 = 2.6
        rep_2 = CanonicalExecutionReport(
            exec_id="EXEC-L2", client_order_id="ORD-L2", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=5, executed_price=2.8, fee=500.0, slippage=0.0,
            timestamp="2026-08-23 09:01:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        )
        self.vssf.account.apply_execution(rep_2)

        pos = self.vssf.account.get_positions()
        self.assertEqual(pos[self.inst_a_key]["qty"], 15)
        self.assertEqual(pos[self.inst_a_key]["side"], "BUY")
        self.assertAlmostEqual(pos[self.inst_a_key]["avg_price"], 2.6, places=4)
        self.assertEqual(self.vssf.account.realized_pnl, 0.0)

        # 3. 부분청산 매도 10 @ 3.2 -> 실현 손익: (3.2 - 2.6) * 10 * 250,000 = 1,500,000 KRW
        rep_3 = CanonicalExecutionReport(
            exec_id="EXEC-L3", client_order_id="ORD-L3", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.SELL,
            executed_qty=10, executed_price=3.2, fee=1000.0, slippage=0.0,
            timestamp="2026-08-23 09:02:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        )
        self.vssf.account.apply_execution(rep_3)

        pos = self.vssf.account.get_positions()
        self.assertEqual(pos[self.inst_a_key]["qty"], 5)
        self.assertEqual(pos[self.inst_a_key]["side"], "BUY")
        self.assertAlmostEqual(pos[self.inst_a_key]["avg_price"], 2.6, places=4)
        self.assertAlmostEqual(self.vssf.account.realized_pnl, 1500000.0, places=2)

        # 4. 완전청산 매도 5 @ 3.5 -> 추가 실현: (3.5 - 2.6) * 5 * 250,000 = 1,125,000 KRW (누적: 2,625,000 KRW)
        rep_4 = CanonicalExecutionReport(
            exec_id="EXEC-L4", client_order_id="ORD-L4", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.SELL,
            executed_qty=5, executed_price=3.5, fee=500.0, slippage=0.0,
            timestamp="2026-08-23 09:03:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        )
        self.vssf.account.apply_execution(rep_4)

        pos = self.vssf.account.get_positions()
        self.assertTrue(self.inst_a_key not in pos or pos[self.inst_a_key]["qty"] == 0)
        self.assertAlmostEqual(self.vssf.account.realized_pnl, 2625000.0, places=2)
        summary = self.vssf.account.get_canonical_summary()
        self.assertEqual(summary.realized_pnl, 2625000.0)
        self.assertEqual(summary.used_margin, 0.0)

    # =========================================================================
    # 2. FILLED: SHORT 라이프사이클 (신규 -> 추가 -> 부분청산 -> 완전청산)
    # =========================================================================

    def test_02_filled_short_full_lifecycle(self):
        """[FILLED - SHORT] 신규 10개 -> 추가 5개 -> 부분청산 10개 -> 완전청산 5개 단계별 정합성."""
        # 1. 신규 SHORT 10 @ 2.5
        rep_1 = CanonicalExecutionReport(
            exec_id="EXEC-S1", client_order_id="ORD-S1", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.SELL,
            executed_qty=10, executed_price=2.5, fee=1000.0, slippage=0.0,
            timestamp="2026-08-23 09:00:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        )
        self.vssf.account.apply_execution(rep_1)

        pos = self.vssf.account.get_positions()
        self.assertEqual(pos[self.inst_a_key]["qty"], 10)
        self.assertEqual(pos[self.inst_a_key]["side"], "SELL")
        self.assertEqual(pos[self.inst_a_key]["avg_price"], 2.5)

        # 2. 추가 SHORT 5 @ 2.2 -> 평단가: (10*2.5 + 5*2.2)/15 = 36.0/15 = 2.4
        rep_2 = CanonicalExecutionReport(
            exec_id="EXEC-S2", client_order_id="ORD-S2", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.SELL,
            executed_qty=5, executed_price=2.2, fee=500.0, slippage=0.0,
            timestamp="2026-08-23 09:01:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        )
        self.vssf.account.apply_execution(rep_2)

        pos = self.vssf.account.get_positions()
        self.assertEqual(pos[self.inst_a_key]["qty"], 15)
        self.assertEqual(pos[self.inst_a_key]["side"], "SELL")
        self.assertAlmostEqual(pos[self.inst_a_key]["avg_price"], 2.4, places=4)

        # 3. 부분청산 매수 10 @ 1.8 -> 실현 손익: (2.4 - 1.8) * 10 * 250,000 = 1,500,000 KRW
        rep_3 = CanonicalExecutionReport(
            exec_id="EXEC-S3", client_order_id="ORD-S3", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=10, executed_price=1.8, fee=1000.0, slippage=0.0,
            timestamp="2026-08-23 09:02:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        )
        self.vssf.account.apply_execution(rep_3)

        pos = self.vssf.account.get_positions()
        self.assertEqual(pos[self.inst_a_key]["qty"], 5)
        self.assertEqual(pos[self.inst_a_key]["side"], "SELL")
        self.assertAlmostEqual(pos[self.inst_a_key]["avg_price"], 2.4, places=4)
        self.assertAlmostEqual(self.vssf.account.realized_pnl, 1500000.0, places=2)

        # 4. 완전청산 매수 5 @ 1.4 -> 추가 실현: (2.4 - 1.4) * 5 * 250,000 = 1,250,000 KRW (누적: 2,750,000 KRW)
        rep_4 = CanonicalExecutionReport(
            exec_id="EXEC-S4", client_order_id="ORD-S4", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=5, executed_price=1.4, fee=500.0, slippage=0.0,
            timestamp="2026-08-23 09:03:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        )
        self.vssf.account.apply_execution(rep_4)

        pos = self.vssf.account.get_positions()
        self.assertTrue(self.inst_a_key not in pos or pos[self.inst_a_key]["qty"] == 0)
        self.assertAlmostEqual(self.vssf.account.realized_pnl, 2750000.0, places=2)

    # =========================================================================
    # 3. REVERSAL: LONG -> SHORT 및 SHORT -> LONG 포지션 반전
    # =========================================================================

    def test_03_position_reversal_lifecycle(self):
        """[REVERSAL] LONG 10 -> SELL 15 (SHORT 5 반전) -> BUY 10 (LONG 5 반전) 정확성."""
        # 1. 초기 LONG 10 @ 2.5
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-REV-1", client_order_id="ORD-REV-1", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=10, executed_price=2.5, fee=1000.0, slippage=0.0,
            timestamp="2026-08-23 09:00:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))

        # 2. 반전 매도 15 @ 3.0 -> 10개 청산 이익: (3.0 - 2.5)*10*250,000 = 1,250,000 KRW, 신규 SHORT 5 @ 3.0
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-REV-2", client_order_id="ORD-REV-2", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.SELL,
            executed_qty=15, executed_price=3.0, fee=1500.0, slippage=0.0,
            timestamp="2026-08-23 09:01:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))

        pos = self.vssf.account.get_positions()
        self.assertEqual(pos[self.inst_a_key]["qty"], 5)
        self.assertEqual(pos[self.inst_a_key]["side"], "SELL")
        self.assertEqual(pos[self.inst_a_key]["avg_price"], 3.0)
        self.assertAlmostEqual(self.vssf.account.realized_pnl, 1250000.0, places=2)

        # 3. 재반전 매수 10 @ 2.0 -> 5개 청산 이익: (3.0 - 2.0)*5*250,000 = 1,250,000 KRW (누적 2,500,000 KRW), 신규 LONG 5 @ 2.0
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-REV-3", client_order_id="ORD-REV-3", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=10, executed_price=2.0, fee=1000.0, slippage=0.0,
            timestamp="2026-08-23 09:02:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))

        pos = self.vssf.account.get_positions()
        self.assertEqual(pos[self.inst_a_key]["qty"], 5)
        self.assertEqual(pos[self.inst_a_key]["side"], "BUY")
        self.assertEqual(pos[self.inst_a_key]["avg_price"], 2.0)
        self.assertAlmostEqual(self.vssf.account.realized_pnl, 2500000.0, places=2)

    # =========================================================================
    # 4. PARTIAL: 부분 체결 및 미체결 잔여분 격리
    # =========================================================================

    def test_04_partial_fill_exact_position_and_unrealized_pnl(self):
        """[PARTIAL] 10개 주문 중 4개 부분 체결 시 포지션=4, 미체결 6개 미반영 검증."""
        # 1. 4개 부분 체결 @ 2.5
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-PART-1", client_order_id="ORD-PART-1", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=4, executed_price=2.5, fee=400.0, slippage=0.0,
            timestamp="2026-08-23 09:00:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))

        pos = self.vssf.account.get_positions()
        self.assertEqual(pos[self.inst_a_key]["qty"], 4)
        self.assertEqual(pos[self.inst_a_key]["side"], "BUY")

        # 시세 2.8로 변동 -> 미실현 손익: (2.8 - 2.5) * 4 * 250,000 = 300,000 KRW
        self.vssf.process_market_data(CanonicalMarketTick(
            timestamp="2026-08-23 09:01:00.000", underlying_price=2.8, seq_id=2
        ))
        self.assertAlmostEqual(self.vssf.account.unrealized_pnl, 300000.0, places=2)

        # 2. 추가 3개 부분 체결 @ 2.8 -> 평단가: (4*2.5 + 3*2.8)/7 = 18.4/7 = 2.62857
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-PART-2", client_order_id="ORD-PART-2", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=3, executed_price=2.8, fee=300.0, slippage=0.0,
            timestamp="2026-08-23 09:02:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))

        pos = self.vssf.account.get_positions()
        self.assertEqual(pos[self.inst_a_key]["qty"], 7)
        self.assertAlmostEqual(pos[self.inst_a_key]["avg_price"], 18.4 / 7.0, places=4)

    # =========================================================================
    # 5. REJECTED: 거부 / 실패 시 포지션 및 손익 무변동
    # =========================================================================

    def test_05_rejected_order_leaves_position_and_pnl_untouched(self):
        """[REJECTED] 체결 실패/거부(executed_qty=0) 투입 시 포지션/손익/잔고 변동 0 검증."""
        # 사전 포지션 생성: 5개 @ 2.5
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-INIT", client_order_id="ORD-INIT", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=5, executed_price=2.5, fee=500.0, slippage=0.0,
            timestamp="2026-08-23 09:00:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))

        pos_before = dict(self.vssf.account.get_positions()[self.inst_a_key])
        snap_before = self.vssf.account.get_canonical_summary()

        # 거부된 리포트 (qty=0) 투입
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-REJ", client_order_id="ORD-REJ", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=0, executed_price=0.0, fee=0.0, slippage=0.0,
            timestamp="2026-08-23 09:01:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))

        pos_after = self.vssf.account.get_positions()[self.inst_a_key]
        snap_after = self.vssf.account.get_canonical_summary()

        self.assertEqual(pos_before["qty"], pos_after["qty"])
        self.assertEqual(pos_before["avg_price"], pos_after["avg_price"])
        self.assertEqual(snap_before.realized_pnl, snap_after.realized_pnl)
        self.assertEqual(snap_before.total_balance, snap_after.total_balance)

    # =========================================================================
    # 6. CANCELLED: 취소 시 포지션 및 손익 무변동
    # =========================================================================

    def test_06_cancelled_order_leaves_position_and_pnl_untouched(self):
        """[CANCELLED] 주문 취소 발생 시 포지션/손익 무변동 확인."""
        pos_count_before = len(self.vssf.account.get_positions())
        snap_before = self.vssf.account.get_canonical_summary()

        # 취소 실행
        cancelled = self.broker.cancel_order("ORD-NON-EXISTENT")
        self.assertFalse(cancelled)  # 미체결 큐에 없으므로 False

        self.assertEqual(len(self.vssf.account.get_positions()), pos_count_before)
        self.assertEqual(self.vssf.account.realized_pnl, snap_before.realized_pnl)

    # =========================================================================
    # 7. ISOLATION: 종목 격리 (CALL 350 vs CALL 360)
    # =========================================================================

    def test_07_instrument_isolation_between_multiple_options(self):
        """[ISOLATION] 종목 A(CALL 350)와 종목 B(CALL 360) 간 포지션 및 손익 독립성 검증."""
        # 종목 A: LONG 10 @ 2.5
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-ISO-A", client_order_id="ORD-ISO-A", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=10, executed_price=2.5, fee=1000.0, slippage=0.0,
            timestamp="2026-08-23 09:00:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))

        # 종목 B: SHORT 20 @ 1.5
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-ISO-B", client_order_id="ORD-ISO-B", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.SELL,
            executed_qty=20, executed_price=1.5, fee=2000.0, slippage=0.0,
            timestamp="2026-08-23 09:01:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=360.0, expiry="2026-09"
        ))

        positions = self.vssf.account.get_positions()
        self.assertEqual(len(positions), 2)
        self.assertEqual(positions[self.inst_a_key]["qty"], 10)
        self.assertEqual(positions[self.inst_a_key]["side"], "BUY")
        self.assertEqual(positions[self.inst_b_key]["qty"], 20)
        self.assertEqual(positions[self.inst_b_key]["side"], "SELL")

        # 종목 A만 전량 청산 @ 3.0 -> 종목 B의 포지션(SHORT 20 @ 1.5)은 100% 보존되어야 함
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-ISO-A-CLOSE", client_order_id="ORD-ISO-A-CLOSE", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.SELL,
            executed_qty=10, executed_price=3.0, fee=1000.0, slippage=0.0,
            timestamp="2026-08-23 09:02:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))

        pos_after = self.vssf.account.get_positions()
        self.assertTrue(self.inst_a_key not in pos_after or pos_after[self.inst_a_key]["qty"] == 0)
        self.assertEqual(pos_after[self.inst_b_key]["qty"], 20)
        self.assertEqual(pos_after[self.inst_b_key]["side"], "SELL")
        self.assertEqual(pos_after[self.inst_b_key]["avg_price"], 1.5)

    # =========================================================================
    # 8. IDEMPOTENCY: 중복 ExecutionReport 수신 멱등성
    # =========================================================================

    def test_08_duplicate_execution_report_idempotency(self):
        """[IDEMPOTENCY] 동일 exec_id 체결 리포트 2회 전달 시 포지션 및 손익 중복 반영 방지."""
        rep = CanonicalExecutionReport(
            exec_id="EXEC-IDEM-001", client_order_id="ORD-IDEM-001", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=10, executed_price=2.5, fee=1000.0, slippage=0.0,
            timestamp="2026-08-23 09:00:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        )

        # 1회차 수신
        self.vssf.account.apply_execution(rep)
        pos_1 = dict(self.vssf.account.get_positions()[self.inst_a_key])
        balance_1 = self.vssf.account.balance

        # 2회차 동일 리포트 수신 (중복)
        self.vssf.account.apply_execution(rep)
        pos_2 = self.vssf.account.get_positions()[self.inst_a_key]
        balance_2 = self.vssf.account.balance

        # 포지션 수량이 20이 아니라 10으로 유지되어야 함
        self.assertEqual(pos_2["qty"], 10)
        self.assertEqual(pos_1["qty"], pos_2["qty"])
        self.assertEqual(balance_1, balance_2)


if __name__ == "__main__":
    unittest.main()
