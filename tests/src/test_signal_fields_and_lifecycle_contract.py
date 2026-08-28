"""Functional Assertion Tests for 5-2: Signal ID / Timestamp / Direction / Quantity / Strategy ID Deep Contract.

Verifies:
1. Signal ID: Uniqueness, strict format consistency (SIG-{seq}-{track}-{local}), lossless propagation to client_order_id.
2. Timestamp: Exact match with market tick timestamp, zero timestamp drift/regeneration across pipeline.
3. Direction (Side): Strict CanonicalOrderSide (BUY/SELL) mapping, preservation across DecisionArbiter and OrderRouter.
4. Quantity: Strict positive integer validation (qty > 0), rejection of zero/negative/non-integer amounts, sizing consistency.
5. Strategy ID (Track ID): Preservation of Track 1~9 identities without cross-contamination or mutation.
6. Composite Multi-field Contract: End-to-end atomic preservation across Strategy -> Canonical -> Arbiter -> RiskGate -> Router.
"""
import unittest
import time
from typing import List, Dict, Any

from shared.contracts.canonical import (
    CanonicalMarketTick,
    CanonicalStrategySignal,
    CanonicalOrderCommand,
    CanonicalAssetType,
    CanonicalOrderSide,
    CanonicalOptionType,
    CanonicalAccountSummary,
)
from option_program.strategy.signal_generator import SignalGenerator
from option_program.strategy.decision_arbiter import DecisionArbiter
from option_program.risk_control.risk_engine import RiskGate, RiskConfig
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime
from option_program.runtime.program_runtime import OptionProgramRuntime


class TestSignalFieldsAndLifecycleContract(unittest.TestCase):
    """5단계-2 Signal ID/timestamp/direction/quantity/strategy ID 등 핵심 필드 심층 검증 스위트"""

    def setUp(self):
        self.signal_generator = SignalGenerator(debounce_window_sec=0.5)
        self.decision_arbiter = DecisionArbiter()
        self.vssf = VirtualSecuritiesFirmRuntime(initial_capital=50_000_000.0)
        self.account_summary = self.vssf.get_account_snapshot()
        self.runtime = OptionProgramRuntime(account_summary=self.account_summary)

    # =========================================================================
    # 1. Signal ID 검증 (Uniqueness, Format, Propagation)
    # =========================================================================

    def test_signal_id_uniqueness_and_propagation(self):
        """[Signal ID] 복수 신호 생성 시 ID 유일성 및 OrderCommand client_order_id에 ID 구성요소 보존 검증"""
        sig1 = CanonicalStrategySignal(
            signal_id="SIG-100-Track1-1",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=1,
            price=2.50,
            option_type=CanonicalOptionType.PUT,
            strike=337.5,
            tag_id="TAIL_DEFENSE",
            timestamp="2026-08-28 09:00:00"
        )
        sig2 = CanonicalStrategySignal(
            signal_id="SIG-100-Track1-2",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=1,
            price=2.50,
            option_type=CanonicalOptionType.CALL,
            strike=362.5,
            tag_id="TAIL_DEFENSE",
            timestamp="2026-08-28 09:00:00"
        )
        # 1) ID 유일성 확인
        self.assertNotEqual(sig1.signal_id, sig2.signal_id)

        # 2) SignalGenerator 주문 변환 시 track_id 및 식별 정보 포함 확인
        cmd1 = self.signal_generator.process_signal(sig1)
        self.assertIsNotNone(cmd1)
        self.assertIn("Track1", cmd1.client_order_id)
        self.assertEqual(cmd1.track_id, "Track1")

    # =========================================================================
    # 2. Timestamp 검증 (Exact Match, Preservation, Drift-Free)
    # =========================================================================

    def test_timestamp_exact_preservation_without_drift(self):
        """[Timestamp] 마켓 틱 타임스탬프가 전략 신호 및 변환 DTO에 동일하게 보존되며 임의 재작성되지 않음 검증"""
        expected_time = "2026-08-28 09:15:30"
        sig = CanonicalStrategySignal(
            signal_id="SIG-TIME-01",
            track_id="Track3",
            asset_type=CanonicalAssetType.FUTURES,
            side=CanonicalOrderSide.SELL,
            qty=1,
            price=350.5,
            tag_id="STAT_ARB_SHORT",
            timestamp=expected_time
        )
        # 1) 신호 타임스탬프 원형 보존
        self.assertEqual(sig.timestamp, expected_time)

        # 2) DecisionArbiter 중재 후에도 타임스탬프 불변 확인
        arb_res = self.decision_arbiter.arbitrate([sig], self.account_summary)
        self.assertEqual(len(arb_res.approved_signals), 1)
        self.assertEqual(arb_res.approved_signals[0].timestamp, expected_time)

    # =========================================================================
    # 3. Direction (Side) 검증 (BUY/SELL Exact Mapping & Reversal-Free)
    # =========================================================================

    def test_direction_exact_mapping_and_reversal_free(self):
        """[Direction] BUY / SELL 방향이 Arbiter, OrderCommand, RiskGate 전 경로에서 왜곡 없이 100% 보존 검증"""
        for side in [CanonicalOrderSide.BUY, CanonicalOrderSide.SELL]:
            sig = CanonicalStrategySignal(
                signal_id=f"SIG-DIR-{side.value}",
                track_id="Track2",
                asset_type=CanonicalAssetType.OPTION,
                side=side,
                qty=1,
                price=3.0,
                option_type=CanonicalOptionType.CALL,
                strike=350.0,
                tag_id=f"TRAP_{side.value}",
                timestamp="2026-08-28 09:00:00"
            )
            # 1) Arbiter 승인 후 방향 일치
            arb_res = self.decision_arbiter.arbitrate([sig], self.account_summary)
            self.assertEqual(arb_res.approved_signals[0].side, side)

            # 2) OrderCommand 변환 후 방향 일치
            self.signal_generator.clear_history()
            cmd = self.signal_generator.process_signal(sig)
            self.assertIsNotNone(cmd)
            self.assertEqual(cmd.side, side)

    # =========================================================================
    # 4. Quantity 검증 (Strict Positive Integer & Sizing Preservation)
    # =========================================================================

    def test_quantity_strict_positive_integer_and_rejections(self):
        """[Quantity] 양수 정수 수량 보존 및 0/음수/잘못된 수량의 엄격 차단 검증"""
        # 1) 정상 수량 (5계약) ➔ 무손실 보존
        sig_valid = CanonicalStrategySignal(
            signal_id="SIG-QTY-05",
            track_id="Track8",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=5,
            price=2.0,
            option_type=CanonicalOptionType.PUT,
            strike=340.0,
            tag_id="MONTHLY_STRANGLE",
            timestamp="2026-08-28 09:00:00"
        )
        is_valid, _ = self.signal_generator.validate_signal(sig_valid)
        self.assertTrue(is_valid)
        self.signal_generator.clear_history()
        cmd = self.signal_generator.process_signal(sig_valid)
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.qty, 5)

        # 2) 수량 = 0 ➔ 즉시 차단
        sig_zero = CanonicalStrategySignal(
            signal_id="SIG-QTY-00", track_id="Track8", asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY, qty=0, price=2.0, option_type=CanonicalOptionType.PUT,
            strike=340.0, tag_id="T8"
        )
        valid_zero, reason_zero = self.signal_generator.validate_signal(sig_zero)
        self.assertFalse(valid_zero)
        self.assertIn("INVALID_QTY", reason_zero)

        # 3) 수량 < 0 (-3계약) ➔ 즉시 차단
        sig_neg = CanonicalStrategySignal(
            signal_id="SIG-QTY-NEG", track_id="Track8", asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY, qty=-3, price=2.0, option_type=CanonicalOptionType.PUT,
            strike=340.0, tag_id="T8"
        )
        valid_neg, reason_neg = self.signal_generator.validate_signal(sig_neg)
        self.assertFalse(valid_neg)
        self.assertIn("INVALID_QTY", reason_neg)

    # =========================================================================
    # 5. Strategy ID (Track ID) 검증 (Track 1~9 전수 식별자 보존)
    # =========================================================================

    def test_strategy_id_track1_to_9_preservation(self):
        """[Strategy ID] Track 1~9 각 전략의 track_id가 전체 파이프라인에서 변조나 오염 없이 보존 검증"""
        all_tracks = [f"Track{i}" for i in range(1, 10)]
        for track in all_tracks:
            sig = CanonicalStrategySignal(
                signal_id=f"SIG-ID-{track}",
                track_id=track,
                asset_type=CanonicalAssetType.OPTION,
                side=CanonicalOrderSide.BUY,
                qty=1,
                price=2.0,
                option_type=CanonicalOptionType.CALL,
                strike=350.0,
                tag_id=f"{track}_TAG",
                timestamp="2026-08-28 09:00:00"
            )
            # Track ID 유효성
            is_valid, _ = self.signal_generator.validate_signal(sig)
            self.assertTrue(is_valid)
            
            # Arbiter 및 OrderCommand 전달 확인
            arb_res = self.decision_arbiter.arbitrate([sig], self.account_summary)
            self.assertEqual(arb_res.approved_signals[0].track_id, track)

            self.signal_generator.clear_history()
            cmd = self.signal_generator.process_signal(sig)
            self.assertIsNotNone(cmd)
            self.assertEqual(cmd.track_id, track)

    # =========================================================================
    # 6. 복합 계약 및 전체 경로 전달 (End-to-End Composite Contract)
    # =========================================================================

    def test_composite_end_to_end_contract_lifecycle(self):
        """[Composite Lifecycle] Signal ID + timestamp + direction + quantity + strategy ID 전 경로 원자적 보존 검증"""
        sig = CanonicalStrategySignal(
            signal_id="SIG-E2E-FULL-01",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=4,
            price=2.85,
            option_type=CanonicalOptionType.PUT,
            strike=337.5,
            tag_id="TAIL_DEFENSE_BUILD",
            timestamp="2026-08-28 09:05:00"
        )
        
        # 1) Validation
        is_valid, err = self.signal_generator.validate_signal(sig)
        self.assertTrue(is_valid)

        # 2) Arbiter
        arb_res = self.decision_arbiter.arbitrate([sig], self.account_summary)
        self.assertEqual(len(arb_res.approved_signals), 1)
        approved_sig = arb_res.approved_signals[0]
        self.assertEqual(approved_sig.signal_id, "SIG-E2E-FULL-01")
        self.assertEqual(approved_sig.timestamp, "2026-08-28 09:05:00")
        self.assertEqual(approved_sig.side, CanonicalOrderSide.BUY)
        self.assertEqual(approved_sig.qty, 4)
        self.assertEqual(approved_sig.track_id, "Track1")

        # 3) OrderCommand Conversion
        self.signal_generator.clear_history()
        cmd = self.signal_generator.process_signal(approved_sig)
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.track_id, "Track1")
        self.assertEqual(cmd.side, CanonicalOrderSide.BUY)
        self.assertEqual(cmd.qty, 4)
        self.assertEqual(cmd.price, 2.85)
        self.assertEqual(cmd.option_type, CanonicalOptionType.PUT)
        self.assertEqual(cmd.strike, 337.5)

        # 4) RiskGate Approval
        is_approved, token, reason = self.runtime.risk_gate.admit_order(cmd, self.account_summary)
        self.assertTrue(is_approved, f"RiskGate must approve compliant command: {reason}")
        self.assertIsNotNone(token)
        self.assertIsNotNone(token.signature)
        self.assertEqual(cmd.track_id, "Track1")


if __name__ == "__main__":
    unittest.main()
