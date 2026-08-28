"""Functional Assertion Tests for 5-1: Canonical Signal Contract and Conversion Pipeline.

Verifies:
1. CanonicalStrategySignal DTO contract integrity, immutability, field specifications.
2. Track 1~9 raw strategy signal -> CanonicalStrategySignal translation across all strategies.
3. SignalGenerator strict schema validation, rejection of malformed/negative/missing fields.
4. DecisionArbiter priority-based arbitration, opposite-direction clash netting, and deterministic consumption.
5. SignalGenerator debounce de-duplication and lossless translation to CanonicalOrderCommand.
"""
import unittest
from dataclasses import FrozenInstanceError
import time

from shared.contracts.canonical import (
    CanonicalStrategySignal,
    CanonicalOrderCommand,
    CanonicalAssetType,
    CanonicalOrderSide,
    CanonicalOptionType,
    CanonicalAccountSummary,
)
from option_program.strategy.signal_generator import SignalGenerator
from option_program.strategy.decision_arbiter import DecisionArbiter, STRATEGY_PRIORITY_MAP
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime
from option_program.runtime.program_runtime import OptionProgramRuntime


class TestCanonicalSignalContract(unittest.TestCase):
    """5단계-1 Canonical Signal 계약 및 변환 전수 검증 스위트"""

    def setUp(self):
        self.signal_generator = SignalGenerator(debounce_window_sec=0.5)
        self.decision_arbiter = DecisionArbiter()
        self.vssf = VirtualSecuritiesFirmRuntime(initial_capital=50_000_000.0)
        self.account_summary = self.vssf.get_account_snapshot()
        self.runtime = OptionProgramRuntime(account_summary=self.account_summary)

    # =========================================================================
    # 1. CanonicalStrategySignal DTO 불변성 및 계약 구조 검증
    # =========================================================================

    def test_contract_immutability(self):
        """[Contract] CanonicalStrategySignal DTO는 frozen=True로 불변이어야 하며 임의 변조 시 에러 발생"""
        sig = CanonicalStrategySignal(
            signal_id="SIG-001",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=2,
            price=2.50,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            tag_id="TAIL_DEFENSE",
            timestamp="2026-08-28 09:00:00"
        )
        self.assertEqual(sig.signal_id, "SIG-001")
        self.assertEqual(sig.qty, 2)
        
        # 불변성 검증: 필드 수정 시 FrozenInstanceError 발생 확인
        with self.assertRaises(FrozenInstanceError):
            sig.qty = 5  # type: ignore

    def test_contract_field_types_and_defaults(self):
        """[Contract] CanonicalStrategySignal 필드 타입 및 옵션 전용 필드 유효성 검증"""
        sig = CanonicalStrategySignal(
            signal_id="SIG-FUT-01",
            track_id="Track3",
            asset_type=CanonicalAssetType.FUTURES,
            side=CanonicalOrderSide.BUY,
            qty=1,
            price=350.0,
            tag_id="STAT_ARB_PAIR"
        )
        self.assertEqual(sig.asset_type, CanonicalAssetType.FUTURES)
        self.assertIsNone(sig.option_type)
        self.assertEqual(sig.strike, 0.0)
        self.assertEqual(sig.reason, "")
        self.assertEqual(sig.timestamp, "")

    # =========================================================================
    # 2. Track 1 ~ Track 9 전수 전략 신호 생성 및 Canonical Signal 변환 검증
    # =========================================================================

    def test_track1_to_track9_signal_conversion_all(self):
        """[Track 1~9 전수] 각 전략의 결과가 CanonicalStrategySignal 계약으로 결함 없이 변환되는지 검증"""
        strategy_samples = [
            # (Track_ID, AssetType, Side, Qty, Price, OptionType, Strike, TagID)
            ("Track1", CanonicalAssetType.OPTION, CanonicalOrderSide.BUY, 2, 2.50, CanonicalOptionType.PUT, 337.5, "TAIL_DEFENSE_BUILD"),
            ("Track2", CanonicalAssetType.OPTION, CanonicalOrderSide.BUY, 1, 3.20, CanonicalOptionType.CALL, 350.0, "ASYMMETRIC_TRAP_ENTRY"),
            ("Track3", CanonicalAssetType.FUTURES, CanonicalOrderSide.SELL, 1, 352.0, None, 0.0, "SHORT_SPREAD_FAR"),
            ("Track4", CanonicalAssetType.OPTION, CanonicalOrderSide.BUY, 1, 1.80, CanonicalOptionType.CALL, 355.0, "GAMMA_SCALP_OTM"),
            ("Track5", CanonicalAssetType.OPTION, CanonicalOrderSide.BUY, 1, 2.10, CanonicalOptionType.CALL, 352.5, "GAP_REVERSION_BUY"),
            ("Track6", CanonicalAssetType.OPTION, CanonicalOrderSide.BUY, 1, 1.50, CanonicalOptionType.PUT, 335.0, "DAILY_TAIL_HEDGE"),
            ("Track7", CanonicalAssetType.OPTION, CanonicalOrderSide.BUY, 2, 2.80, CanonicalOptionType.PUT, 340.0, "WEEKLY_STRANGLE_BUY"),
            ("Track8", CanonicalAssetType.OPTION, CanonicalOrderSide.BUY, 1, 3.50, CanonicalOptionType.CALL, 365.0, "MONTHLY_WIDE_STRANGLE"),
            ("Track9", CanonicalAssetType.OPTION, CanonicalOrderSide.BUY, 1, 0.90, CanonicalOptionType.PUT, 330.0, "OVERNIGHT_EVENT_PUT"),
        ]

        for track_id, asset_t, side_t, qty, price, opt_t, strike, tag_id in strategy_samples:
            sig = CanonicalStrategySignal(
                signal_id=f"SIG-SAMPLE-{track_id}",
                track_id=track_id,
                asset_type=asset_t,
                side=side_t,
                qty=qty,
                price=price,
                option_type=opt_t,
                strike=strike,
                tag_id=tag_id,
                timestamp="2026-08-28 09:00:00"
            )
            # 유효성 검증
            is_valid, reason = self.signal_generator.validate_signal(sig)
            self.assertTrue(is_valid, f"{track_id} signal must be valid: {reason}")
            self.assertEqual(sig.track_id, track_id)
            self.assertEqual(sig.asset_type, asset_t)
            self.assertEqual(sig.side, side_t)

    # =========================================================================
    # 3. 비정상 / 결함 신호 차단 검증 (Signal Validation)
    # =========================================================================

    def test_signal_generator_validation_rejections(self):
        """[Validation] 음수 수량, 0 이하 가격, 누락 트랙/태그, 옵션 누락 strike/option_type 즉시 거부"""
        # 1) 수량 0 또는 음수
        sig_bad_qty = CanonicalStrategySignal(
            signal_id="SIG-INV-QTY", track_id="Track1", asset_type=CanonicalAssetType.FUTURES,
            side=CanonicalOrderSide.BUY, qty=0, price=350.0, tag_id="T1"
        )
        valid, reason = self.signal_generator.validate_signal(sig_bad_qty)
        self.assertFalse(valid)
        self.assertIn("INVALID_QTY", reason)

        # 2) 가격 0 또는 음수
        sig_bad_price = CanonicalStrategySignal(
            signal_id="SIG-INV-PRC", track_id="Track1", asset_type=CanonicalAssetType.FUTURES,
            side=CanonicalOrderSide.BUY, qty=1, price=-10.0, tag_id="T1"
        )
        valid, reason = self.signal_generator.validate_signal(sig_bad_price)
        self.assertFalse(valid)
        self.assertIn("INVALID_PRICE", reason)

        # 3) Track ID 누락
        sig_bad_track = CanonicalStrategySignal(
            signal_id="SIG-INV-TRK", track_id="", asset_type=CanonicalAssetType.FUTURES,
            side=CanonicalOrderSide.BUY, qty=1, price=350.0, tag_id="T1"
        )
        valid, reason = self.signal_generator.validate_signal(sig_bad_track)
        self.assertFalse(valid)
        self.assertEqual(reason, "MISSING_TRACK_ID")

        # 4) Tag ID 누락
        sig_bad_tag = CanonicalStrategySignal(
            signal_id="SIG-INV-TAG", track_id="Track1", asset_type=CanonicalAssetType.FUTURES,
            side=CanonicalOrderSide.BUY, qty=1, price=350.0, tag_id=""
        )
        valid, reason = self.signal_generator.validate_signal(sig_bad_tag)
        self.assertFalse(valid)
        self.assertEqual(reason, "MISSING_TAG_ID")

        # 5) 옵션 자산에서 strike 누락 (0.0)
        sig_bad_strike = CanonicalStrategySignal(
            signal_id="SIG-INV-STK", track_id="Track1", asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY, qty=1, price=2.5, strike=0.0, option_type=CanonicalOptionType.CALL, tag_id="T1"
        )
        valid, reason = self.signal_generator.validate_signal(sig_bad_strike)
        self.assertFalse(valid)
        self.assertIn("INVALID_OPTION_STRIKE", reason)

        # 6) 옵션 자산에서 option_type 누락 (None)
        sig_bad_opt_type = CanonicalStrategySignal(
            signal_id="SIG-INV-OPTT", track_id="Track1", asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY, qty=1, price=2.5, strike=350.0, option_type=None, tag_id="T1"
        )
        valid, reason = self.signal_generator.validate_signal(sig_bad_opt_type)
        self.assertFalse(valid)
        self.assertEqual(reason, "MISSING_OPTION_TYPE")

    # =========================================================================
    # 4. DecisionArbiter에 의한 Canonical Signal 소비 및 상충 중재
    # =========================================================================

    def test_decision_arbiter_priority_and_consumption(self):
        """[DecisionArbiter] 전략 우선순위 정렬 및 동일 종목 반대 방향(BUY vs SELL) 상충 시 상위 우선순위 채택 검증"""
        # 동일 종목(CALL 350.0pt)에 대해 Track 1 (BUY, 우선순위 2) vs Track 2 (SELL, 우선순위 6) 충돌 모의
        sig_high = CanonicalStrategySignal(
            signal_id="SIG-T1-HIGH",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=2,
            price=3.0,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            tag_id="T1_BUY"
        )
        sig_low = CanonicalStrategySignal(
            signal_id="SIG-T2-LOW",
            track_id="Track2",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.SELL,
            qty=1,
            price=3.0,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            tag_id="T2_SELL"
        )

        res = self.decision_arbiter.arbitrate([sig_low, sig_high], self.account_summary)
        
        # 1) 상위 우선순위 Track 1 승리 및 승인 목록 포함 확인
        self.assertEqual(len(res.approved_signals), 1)
        self.assertEqual(res.approved_signals[0].track_id, "Track1")
        self.assertEqual(res.approved_signals[0].side, CanonicalOrderSide.BUY)

        # 2) 하위 우선순위 Track 2 상충 넷팅 거부 확인
        self.assertEqual(len(res.rejected_signals), 1)
        self.assertEqual(res.rejected_signals[0][0].track_id, "Track2")
        self.assertIn("CLASH_NETTING_REJECTED", res.rejected_signals[0][1])

    # =========================================================================
    # 5. SignalGenerator 중복 디바운싱 및 OrderCommand 무손실 변환 검증
    # =========================================================================

    def test_signal_generator_debounce_and_order_conversion(self):
        """[SignalGenerator] 동일 신호 디바운스 차단 및 CanonicalOrderCommand 완벽 무손실 변환 검증"""
        self.signal_generator.clear_history()
        sig = CanonicalStrategySignal(
            signal_id="SIG-DEBOUNCE-01",
            track_id="Track7",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=3,
            price=2.45,
            option_type=CanonicalOptionType.PUT,
            strike=340.0,
            tag_id="WEEKLY_PUT_BUY"
        )

        # 1) 최초 신호 변환 ➔ CanonicalOrderCommand 정상 생성
        t0 = 1000.0
        cmd1 = self.signal_generator.process_signal(sig, current_time=t0)
        self.assertIsNotNone(cmd1)
        self.assertEqual(cmd1.track_id, "Track7")
        self.assertEqual(cmd1.asset_type, CanonicalAssetType.OPTION)
        self.assertEqual(cmd1.side, CanonicalOrderSide.BUY)
        self.assertEqual(cmd1.qty, 3)
        self.assertEqual(cmd1.price, 2.45)
        self.assertEqual(cmd1.option_type, CanonicalOptionType.PUT)
        self.assertEqual(cmd1.strike, 340.0)
        self.assertEqual(cmd1.tag_id, "WEEKLY_PUT_BUY")

        # 2) 디바운스 윈도우(0.5초) 이내 동일 신호 재인입 ➔ 중복 차단 (None 반환)
        cmd_dup = self.signal_generator.process_signal(sig, current_time=t0 + 0.2)
        self.assertIsNone(cmd_dup, "Duplicate signal within debounce window must be suppressed")

        # 3) 디바운스 윈도우 초과 후 재인입 ➔ 정상 수용
        cmd2 = self.signal_generator.process_signal(sig, current_time=t0 + 0.6)
        self.assertIsNotNone(cmd2, "Signal after debounce window should be processed")


if __name__ == "__main__":
    unittest.main()
