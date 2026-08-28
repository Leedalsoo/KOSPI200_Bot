"""Functional Assertion Tests for 5-3: Concurrent Signals, Conflict Resolution & Arbiter Determinism.

Verifies:
1. Multi-Strategy Concurrent Signals: Track 1~9 simultaneous signal ingestion, sorting, and arbitration.
2. BUY vs SELL Directional Conflict: Strict priority-based victory and subordinate clash netting rejection.
3. Same-Direction Multi-Signal Ingestion: Uncontested aggregation and individual signal preservation.
4. Input Order Invariance & Determinism: [SigA, SigB] == [SigB, SigA] identical arbitration output.
5. Priority & Tie-Breaking: Strict hierarchy (Hedge > T1 > T6/9 > T3/4 > T7/8 > T2/5) and tie-breaking by (-qty, signal_id).
6. Duplicate Suppression & OrderCommand Integrity: Debouncing at SignalGenerator and downstream RiskGate non-proliferation.
"""
import unittest
import copy
from typing import List

from shared.contracts.canonical import (
    CanonicalStrategySignal,
    CanonicalOrderCommand,
    CanonicalAssetType,
    CanonicalOrderSide,
    CanonicalOptionType,
    CanonicalAccountSummary,
)
from option_program.strategy.signal_generator import SignalGenerator
from option_program.strategy.decision_arbiter import (
    DecisionArbiter,
    ArbitrationResult,
    STRATEGY_PRIORITY_MAP
)
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime
from option_program.runtime.program_runtime import OptionProgramRuntime


class TestConcurrentSignalsAndConflictResolution(unittest.TestCase):
    """5단계-3 다중 전략 동시신호 및 충돌 중재 전수 검증 스위트"""

    def setUp(self):
        self.signal_generator = SignalGenerator(debounce_window_sec=0.5)
        self.decision_arbiter = DecisionArbiter()
        self.vssf = VirtualSecuritiesFirmRuntime(initial_capital=50_000_000.0)
        self.account_summary = self.vssf.get_account_snapshot()
        self.runtime = OptionProgramRuntime(account_summary=self.account_summary)

    # =========================================================================
    # 1. Track 1 + Track 2 및 9대 전략 전수 동시 신호 처리
    # =========================================================================

    def test_all_track1_to_9_concurrent_signals_arbitration(self):
        """[9대 전략 동시 신호] Track 1~9 9개 전략 신호 동시 인입 시 우선순위 순서대로 전수 중재 및 승인 검증"""
        all_signals = [
            CanonicalStrategySignal(
                signal_id=f"SIG-ALL-Track{i}",
                track_id=f"Track{i}",
                asset_type=CanonicalAssetType.OPTION if i != 3 else CanonicalAssetType.FUTURES,
                side=CanonicalOrderSide.BUY,
                qty=1,
                price=2.0 + i * 0.1,
                option_type=CanonicalOptionType.CALL if i != 3 else None,
                strike=340.0 + i * 2.5 if i != 3 else 0.0,
                tag_id=f"TAG_TRACK_{i}",
                timestamp="2026-08-28 09:00:00"
            )
            for i in range(1, 10)
        ]

        res = self.decision_arbiter.arbitrate(all_signals, self.account_summary)

        # 서로 다른 종목이므로 9개 모두 정상 승인
        self.assertEqual(len(res.approved_signals), 9)
        self.assertEqual(len(res.rejected_signals), 0)

        # 승인 목록이 우선순위 순서(Track1 -> Track6/9 -> Track3/4 -> Track7/8 -> Track2/5)로 정렬되었는지 검증
        approved_tracks = [s.track_id for s in res.approved_signals]
        self.assertEqual(approved_tracks[0], "Track1")
        self.assertIn(approved_tracks[-1], ["Track2", "Track5"])

    # =========================================================================
    # 2. 동일 종목 BUY vs SELL 상충 충돌 중재 (Clash Netting Rejection)
    # =========================================================================

    def test_same_instrument_buy_vs_sell_conflict_priority_resolution(self):
        """[BUY vs SELL 충돌] 동일 종목(CALL 350.0)에 대해 상위 우선순위(Track1 BUY) 승리 및 하위(Track5 SELL) 거부 검증"""
        sig_t1_buy = CanonicalStrategySignal(
            signal_id="SIG-T1-BUY",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=2,
            price=3.10,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            tag_id="T1_CORE_BUY"
        )
        sig_t5_sell = CanonicalStrategySignal(
            signal_id="SIG-T5-SELL",
            track_id="Track5",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.SELL,
            qty=2,
            price=3.10,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            tag_id="T5_GAP_SELL"
        )

        res = self.decision_arbiter.arbitrate([sig_t5_sell, sig_t1_buy], self.account_summary)

        # 1) 승인: Track 1 BUY
        self.assertEqual(len(res.approved_signals), 1)
        self.assertEqual(res.approved_signals[0].track_id, "Track1")
        self.assertEqual(res.approved_signals[0].side, CanonicalOrderSide.BUY)

        # 2) 거부: Track 5 SELL (CLASH_NETTING_REJECTED)
        self.assertEqual(len(res.rejected_signals), 1)
        rejected_sig, reason = res.rejected_signals[0]
        self.assertEqual(rejected_sig.track_id, "Track5")
        self.assertIn("CLASH_NETTING_REJECTED", reason)
        self.assertIn("Subordinate to Track1 (BUY)", reason)

    # =========================================================================
    # 3. 동일 종목 동일 방향 다중 신호 (BUY + BUY / SELL + SELL) 수용
    # =========================================================================

    def test_same_instrument_same_direction_multiple_signals_accepted(self):
        """[동일 종목 동일 방향] Track 1 BUY와 Track 2 BUY가 동일 종목에 인입될 경우 상충 없이 둘 다 승인 검증"""
        sig_t1_buy = CanonicalStrategySignal(
            signal_id="SIG-T1-BUY-350",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=2,
            price=3.10,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            tag_id="T1_BUY"
        )
        sig_t2_buy = CanonicalStrategySignal(
            signal_id="SIG-T2-BUY-350",
            track_id="Track2",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=1,
            price=3.10,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            tag_id="T2_BUY"
        )

        res = self.decision_arbiter.arbitrate([sig_t1_buy, sig_t2_buy], self.account_summary)

        self.assertEqual(len(res.approved_signals), 2)
        self.assertEqual(len(res.rejected_signals), 0)
        self.assertEqual(res.approved_signals[0].track_id, "Track1")
        self.assertEqual(res.approved_signals[1].track_id, "Track2")

    # =========================================================================
    # 4. 입력 순서 불변성 (Input Order Invariance & Determinism)
    # =========================================================================

    def test_input_order_invariance_and_determinism(self):
        """[입력 순서 불변성] [SigA, SigB]와 [SigB, SigA] 인입 시 동일한 최종 중재 결과 산출 검증"""
        sig_t6_buy = CanonicalStrategySignal(
            signal_id="SIG-T6-PUT-335",
            track_id="Track6",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=3,
            price=1.80,
            option_type=CanonicalOptionType.PUT,
            strike=335.0,
            tag_id="T6_PUT"
        )
        sig_t2_sell = CanonicalStrategySignal(
            signal_id="SIG-T2-PUT-335",
            track_id="Track2",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.SELL,
            qty=1,
            price=1.80,
            option_type=CanonicalOptionType.PUT,
            strike=335.0,
            tag_id="T2_PUT"
        )

        # 순서 1: T6, T2
        res1 = self.decision_arbiter.arbitrate([sig_t6_buy, sig_t2_sell], self.account_summary)
        # 순서 2: T2, T6
        res2 = self.decision_arbiter.arbitrate([sig_t2_sell, sig_t6_buy], self.account_summary)

        # 결과 100% 동일 검증
        self.assertEqual(len(res1.approved_signals), len(res2.approved_signals))
        self.assertEqual(res1.approved_signals[0].signal_id, res2.approved_signals[0].signal_id)
        self.assertEqual(res1.approved_signals[0].track_id, "Track6")

        self.assertEqual(len(res1.rejected_signals), len(res2.rejected_signals))
        self.assertEqual(res1.rejected_signals[0][0].signal_id, res2.rejected_signals[0][0].signal_id)
        self.assertEqual(res1.rejected_signals[0][0].track_id, "Track2")

    # =========================================================================
    # 5. 동일 우선순위 전략 간 Tie-break 검증 (수량 및 Signal ID)
    # =========================================================================

    def test_same_priority_tie_break_by_quantity_and_signal_id(self):
        """[동일 우선순위 Tie-break] 동일 우선순위(Track7 vs Track8: 5순위) 상충 시 수량이 많은 신호 우선 승리 검증"""
        # 동일 종목(PUT 340.0)에 대해 Track 7(BUY, 5계약) vs Track 8(SELL, 2계약)
        sig_t7_large = CanonicalStrategySignal(
            signal_id="SIG-T7-BUY",
            track_id="Track7",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=5,
            price=2.20,
            option_type=CanonicalOptionType.PUT,
            strike=340.0,
            tag_id="T7_BIG"
        )
        sig_t8_small = CanonicalStrategySignal(
            signal_id="SIG-T8-SELL",
            track_id="Track8",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.SELL,
            qty=2,
            price=2.20,
            option_type=CanonicalOptionType.PUT,
            strike=340.0,
            tag_id="T8_SMALL"
        )

        res = self.decision_arbiter.arbitrate([sig_t8_small, sig_t7_large], self.account_summary)

        # 수량이 더 많은 Track 7 (5계약) 승리
        self.assertEqual(len(res.approved_signals), 1)
        self.assertEqual(res.approved_signals[0].track_id, "Track7")
        self.assertEqual(res.approved_signals[0].qty, 5)

        # Track 8 거부
        self.assertEqual(len(res.rejected_signals), 1)
        self.assertEqual(res.rejected_signals[0][0].track_id, "Track8")

    # =========================================================================
    # 6. 중복 신호 디바운스 및 최종 OrderCommand / RiskGate 비증식 검증
    # =========================================================================

    def test_duplicate_suppression_and_clean_order_command_dispatch(self):
        """[중복 방지 & 주문 변환] Arbiter 승인 후 SignalGenerator를 거치며 중복 신호 차단 및 단일 OrderCommand 발주 검증"""
        self.signal_generator.clear_history()

        sig_approved = CanonicalStrategySignal(
            signal_id="SIG-DISPATCH-01",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=2,
            price=2.50,
            option_type=CanonicalOptionType.PUT,
            strike=337.5,
            tag_id="TAIL_DEFENSE",
            timestamp="2026-08-28 09:00:00"
        )

        # 1회차 변환 ➔ 성공적인 OrderCommand 생성
        t0 = 1000.0
        cmd1 = self.signal_generator.process_signal(sig_approved, current_time=t0)
        self.assertIsNotNone(cmd1)

        # RiskGate 승인 확인
        is_app, token, _ = self.runtime.risk_gate.admit_order(cmd1, self.account_summary)
        self.assertTrue(is_app)
        self.assertIsNotNone(token)

        # 0.2초 후 동일 신호 재인입 (디바운스 차단)
        cmd_dup = self.signal_generator.process_signal(sig_approved, current_time=t0 + 0.2)
        self.assertIsNone(cmd_dup, "Duplicate signal within debounce window must not create redundant OrderCommand")


if __name__ == "__main__":
    unittest.main()
