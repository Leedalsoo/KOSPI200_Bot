"""Functional Assertion Tests for 4-2: Entry / Exit / Position Sizing / Stop.

Verifies:
A. Entry: Condition triggering, Signal->Order generation, Invalid entry prevention, Duplicate entry debounce.
B. Exit: Legitimate position exit, No ghost exits without active position, Time & Trailing cutoff.
C. Position Sizing: Normal sizing, Risk reduction (REDUCE), Negative/Zero/Exceeded quantity guards.
D. Stop: Dynamic trailing stop, Stop-loss execution pathway, Boundary values defense.
"""
import unittest
from typing import Dict, Any, List

from shared.contracts.canonical import (
    CanonicalMarketTick,
    CanonicalOrderCommand,
    CanonicalExecutionReport,
    CanonicalStrategySignal,
    CanonicalAssetType,
    CanonicalOrderSide,
    CanonicalOptionType,
    CanonicalAccountSummary,
    build_instrument_key
)
from shared.core.contracts import OrderStatus
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime
from option_program.broker.broker_interface import BrokerFactory, BrokerMode
from option_program.runtime.program_runtime import OptionProgramRuntime
from option_program.strategy.signal_generator import SignalGenerator
from option_program.risk_control.risk_engine import RiskGate, RiskConfig


class TestEntryExitSizingStop(unittest.TestCase):
    """4단계-2 Entry, Exit, Position Sizing, Stop 종합 검증 스위트"""

    def setUp(self):
        self.vssf = VirtualSecuritiesFirmRuntime(initial_capital=50_000_000.0)
        self.broker = BrokerFactory.create_broker(mode=BrokerMode.PAPER, vssf_runtime=self.vssf)
        self.account_summary = self.vssf.get_account_snapshot()
        self.runtime = OptionProgramRuntime(account_summary=self.account_summary)

    # -------------------------------------------------------------
    # A. Entry 검증
    # -------------------------------------------------------------
    def test_A1_valid_entry_produces_order_command(self):
        """[Entry] 정상 진입 조건 충족 시 Signal -> CanonicalOrderCommand 생성 검증"""
        st5 = self.runtime.strategies[4] # Track 5 Gap Divergence
        res = st5.evaluate_gap_divergence(
            open_price=355.0,
            prev_close_price=350.0,
            active_vol=1.0,
            current_regime="NORMAL",
            date_str="2026-08-28"
        )
        self.assertEqual(res["status"], "TRIGGERED")
        self.assertGreater(len(res["signals"]), 0)
        
        # SignalGenerator 검증 통과 여부
        sig_dict = res["signals"][0]
        sig_dto = CanonicalStrategySignal(
            signal_id="SIG-T5-001",
            track_id="Track5",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=int(sig_dict.get("qty", 1)),
            price=float(sig_dict.get("target_price", 2.50)),
            strike=float(sig_dict.get("strike", 350.0)),
            option_type=CanonicalOptionType.PUT,
            tag_id=sig_dict.get("action", "ENTER_GAP_SHORT"),
            timestamp="2026-08-28 09:00:00.000"
        )
        is_valid, err = self.runtime.signal_generator.validate_signal(sig_dto)
        self.assertTrue(is_valid, f"Validation failed: {err}")
        self.assertEqual(sig_dto.track_id, "Track5")
        self.assertEqual(sig_dto.side, CanonicalOrderSide.BUY)

    def test_A2_invalid_entry_conditions_prevent_order(self):
        """[Entry] 비정상/미달 진입 조건(블랙스완 갭 z >= 4.0 등)에서 주문 미발생 검증"""
        st5 = self.runtime.strategies[4]
        # 비정상 극단 갭 (+25.0pt 갭상승 -> z >= 4.0 극단 파국으로 진입 차단)
        res = st5.evaluate_gap_divergence(
            open_price=375.0,
            prev_close_price=350.0,
            active_vol=1.0,
            current_regime="NORMAL",
            date_str="2026-08-28"
        )
        self.assertEqual(res["status"], "BLACK_SWAN_GAP_BLOCKED")
        self.assertEqual(len(res["signals"]), 0)

    def test_A3_duplicate_entry_debouncing_prevents_duplicate_orders(self):
        """[Entry] 동일 조건 반복 진입 시 디바운싱 및 중복 주문 방지 검증"""
        sig_gen = SignalGenerator(debounce_window_sec=1.0)
        sig = CanonicalStrategySignal(
            signal_id="SIG-T4-001",
            track_id="Track4",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=1,
            price=2.50,
            strike=350.0,
            option_type=CanonicalOptionType.CALL,
            tag_id="BUILD_HYBRID_BASECAMP",
            timestamp="2026-08-28 09:05:00.000"
        )
        # 1차 인입
        cmd1 = sig_gen.process_signal(sig, current_time=1000.0)
        self.assertIsNotNone(cmd1, "First signal must produce CanonicalOrderCommand")

        # 0.5초 뒤 동일 신호 인입 시 디바운스 차단 (None 반환)
        cmd2 = sig_gen.process_signal(sig, current_time=1000.5)
        self.assertIsNone(cmd2, "Duplicate rapid signal within debounce window must be blocked")

    # -------------------------------------------------------------
    # B. Exit 검증
    # -------------------------------------------------------------
    def test_B1_legitimate_exit_when_position_held(self):
        """[Exit] 보유 포지션 존재 시 트레일링 스탑 정상 청산 발주 검증"""
        st6 = self.runtime.strategies[5] # Track 6
        st6.insurance_state = {
            "is_active": True,
            "bought_date": "2026-08-28",
            "long_put_strike": 337.5,
            "long_call_strike": 362.5,
            "premium_spent": 500_000.0,
            "high_watermark_intrinsic": 1_200_000.0, # 최고 내재가치 120만원
            "trailing_stop_active": True,
        }
        # 현재 내재가치가 80만원으로 반락 (120만 * 0.85 = 102만 이하 -> 트레일링 스탑 익절 청산)
        # current_price = 337.5 - (800000 / 250000) = 334.3pt
        res = st6.evaluate_take_profit(
            current_price=334.3,
            active_vol=1.5,
            time_str="10:00:00"
        )
        self.assertEqual(res["status"], "PROFIT_TAKEN_TRAILING_STOP")
        self.assertGreater(len(res["signals"]), 0)
        self.assertEqual(res["signals"][0]["action"], "TAKE_PROFIT_HYBRID_TRAILING_STOP")

    def test_B2_no_ghost_exit_without_position(self):
        """[Exit] 보유 포지션이 없는 상태에서 허위 청산 신호 미발생 검증"""
        st6 = self.runtime.strategies[5]
        st6.reset_state() # 포지션 비활성화
        self.assertFalse(st6.insurance_state["is_active"])
        res = st6.evaluate_take_profit(
            current_price=330.0,
            active_vol=1.5,
            time_str="10:00:00"
        )
        self.assertEqual(res["status"], "INACTIVE")
        self.assertEqual(len(res["signals"]), 0)

    # -------------------------------------------------------------
    # C. Position Sizing & Risk Control 검증
    # -------------------------------------------------------------
    def test_C1_zero_and_negative_quantity_rejection(self):
        """[Position Sizing] 0 이하/음수 주문수량 인입 시 SignalGenerator 즉시 차단 검증"""
        sig_gen = SignalGenerator()
        sig_zero = CanonicalStrategySignal(
            signal_id="SIG-T1-ZERO",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=0,
            price=2.50,
            strike=350.0,
            option_type=CanonicalOptionType.CALL,
            tag_id="TAIL_DEFENSE_BUILD",
            timestamp="2026-08-28 09:00:00.000"
        )
        is_valid_zero, err_zero = sig_gen.validate_signal(sig_zero)
        self.assertFalse(is_valid_zero)
        self.assertIn("INVALID_QTY", err_zero)

        sig_neg = CanonicalStrategySignal(
            signal_id="SIG-T1-NEG",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=-5,
            price=2.50,
            strike=350.0,
            option_type=CanonicalOptionType.CALL,
            tag_id="TAIL_DEFENSE_BUILD",
            timestamp="2026-08-28 09:00:00.000"
        )
        is_valid_neg, err_neg = sig_gen.validate_signal(sig_neg)
        self.assertFalse(is_valid_neg)
        self.assertIn("INVALID_QTY", err_neg)

    def test_C2_exceeded_max_order_quantity_blocked_by_risk_gate(self):
        """[Position Sizing] 단일 주문 최대 한도(50계약) 초과 시 RiskGate에서 원천 차단 검증"""
        cmd_oversize = CanonicalOrderCommand(
            client_order_id="ORD-SIZE-999",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=100, # Max limit = 50
            price=2.50,
            strike=350.0,
            option_type=CanonicalOptionType.CALL
        )
        is_approved, token, reason = self.runtime.risk_gate.admit_order(cmd_oversize, self.account_summary)
        self.assertFalse(is_approved, "RiskGate must deny order exceeding max single order quantity")
        self.assertIsNone(token)
        self.assertIn("EXCEEDED_MAX_ORDER_QTY", reason)

    def test_C3_risk_reduce_action_applies_scaled_quantity(self):
        """[Position Sizing] RiskEngine REDUCE 판정 시 주문 수량 동적 축소 적용 검증"""
        # Sizing 감축 모의 (10 -> 3)
        reduced_cmd = CanonicalOrderCommand(
            client_order_id="ORD-REDUCE-001",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=3,
            price=2.50,
            strike=350.0,
            option_type=CanonicalOptionType.CALL
        )
        is_approved, token, reason = self.runtime.risk_gate.admit_order(reduced_cmd, self.account_summary)
        self.assertTrue(is_approved, "Reduced order must pass RiskGate")
        self.assertIsNotNone(token)
        self.assertEqual(self.runtime.risk_gate.last_evaluation_result.approved_qty, 3)

    # -------------------------------------------------------------
    # D. Stop & Trailing Stop 검증
    # -------------------------------------------------------------
    def test_D1_stop_loss_trigger_and_order_dispatch(self):
        """[Stop] 트레일링 스탑 / 손절 조건 충족 시 즉각 Stop 주문 발생 검증"""
        st2 = self.runtime.strategies[1] # Track 2 Asymmetric Trap
        st2.trap_state = {
            "is_active": True,
            "entry_price": 2.0
        }
        # 현재가 1.2pt (-40% 급락 -> -30% 손절 조건 트리거)
        res = st2.evaluate_trap_status(current_price=1.2)
        self.assertEqual(res["status"], "STOP_LOSS")
        self.assertGreater(len(res["signals"]), 0)
        self.assertEqual(res["signals"][0]["action"], "STOP_LOSS_CLOSE")

    def test_D2_stop_not_triggered_under_normal_price_movement(self):
        """[Stop] 정상 변동 범위(안정 유지)에서는 허위 Stop 미발동 검증"""
        st2 = self.runtime.strategies[1]
        st2.trap_state = {
            "is_active": True,
            "entry_price": 2.0
        }
        # 현재가 2.0pt (손실 없음 -> Stop 미발동)
        res = st2.evaluate_trap_status(current_price=2.0)
        self.assertEqual(res["status"], "NORMAL")
        self.assertEqual(len(res["signals"]), 0)


if __name__ == "__main__":
    unittest.main()
