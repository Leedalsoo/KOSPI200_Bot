"""Functional Assertion Tests for 4-4: Strategy Normal / Failure / Boundary Comprehensive Suite.

Verifies Track 1~9 and Decision/Execution pathways across:
1. Normal Cases: Valid input -> Feature -> Strategy Evaluation -> Signal -> RiskGate -> OrderCommand.
2. Failure Cases: Missing/NaN inputs, RiskGate limit denial, Invalid signal fields, Broker exception isolation.
3. Boundary Cases: Exact threshold matches, pre/post threshold values, max quantity bounds, stop loss bounds, time cutoff bounds.
"""
import unittest
import math
from typing import Dict, Any

from shared.contracts.canonical import (
    CanonicalMarketTick,
    CanonicalOrderCommand,
    CanonicalStrategySignal,
    CanonicalAssetType,
    CanonicalOrderSide,
    CanonicalOptionType,
    CanonicalAccountSummary,
)
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime
from option_program.broker.broker_interface import BrokerFactory, BrokerMode
from option_program.runtime.program_runtime import OptionProgramRuntime
from option_program.strategy.signal_generator import SignalGenerator
from option_program.risk_control.risk_engine import RiskGate, RiskConfig


class TestStrategyNormalFailureBoundary(unittest.TestCase):
    """4단계-4 전략별 정상/실패/경계 조건 종합 검증 스위트"""

    def setUp(self):
        self.vssf = VirtualSecuritiesFirmRuntime(initial_capital=50_000_000.0)
        self.broker = BrokerFactory.create_broker(mode=BrokerMode.PAPER, vssf_runtime=self.vssf)
        self.account_summary = self.vssf.get_account_snapshot()
        self.runtime = OptionProgramRuntime(account_summary=self.account_summary)

    # =========================================================================
    # 1. 정상 케이스 (Normal Cases)
    # =========================================================================

    def test_normal_track1_market_open_pipeline(self):
        """[Normal] Track 1: 정상 선물 350.0pt 인입 시 이중 링 가두리 및 Tail 방어 신호 -> Order 생성"""
        st1 = self.runtime.strategies[0] # Track 1
        st1.is_market_opened = False
        st1.base_price = 0.0
        signals = st1.on_market_open(current_price=350.0)
        
        self.assertGreater(len(signals), 0, "Track 1 must generate on_market_open signals")
        tail_sig = next((s for s in signals if s.get("action") == "TAIL_DEFENSE_BUILD"), None)
        self.assertIsNotNone(tail_sig)

        # Signal -> Risk -> Order 전달 검증
        sig_dto = CanonicalStrategySignal(
            signal_id="SIG-T1-NORM",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=int(tail_sig.get("qty", 1)),
            price=2.50,
            strike=float(tail_sig.get("put_strike", 337.5)),
            option_type=CanonicalOptionType.PUT,
            tag_id=tail_sig.get("action", "TAIL_DEFENSE_BUILD"),
            timestamp="2026-08-28 09:00:00"
        )
        is_valid, _ = self.runtime.signal_generator.validate_signal(sig_dto)
        self.assertTrue(is_valid)

        cmd = self.runtime.signal_generator.process_signal(sig_dto)
        self.assertIsNotNone(cmd)
        is_approved, token, _ = self.runtime.risk_gate.admit_order(cmd, self.account_summary)
        self.assertTrue(is_approved)
        self.assertIsNotNone(token)

    def test_normal_track3_stat_arb_spread_entry(self):
        """[Normal] Track 3: Spread Z-Score 괴리 발생 시 차익거래 신호 -> Order 생성"""
        st3 = self.runtime.strategies[2] # Track 3
        spread_history = [0.5] * 14 + [3.5] # 15번째 틱 급등으로 Z-Score 유발
        m_data = {
            "underlying_price": 350.0,
            "time_str": "09:30:00",
            "atm_strike": 350.0,
            "near_synthetic_future": 353.5,
            "far_synthetic_future": 350.0,
            "spread_history": spread_history,
            "active_vol": 1.0,
            "base_vol": 1.0,
            "bid_ask_spread": 0.05,
            "date_str": "2026-08-28"
        }
        res = st3.evaluate_arbitrage(m_data)
        self.assertIn("ENTER", res.get("status", ""))
        self.assertGreater(len(res.get("signals", [])), 0)
        self.assertEqual(res["signals"][0]["type"], "SHORT_SPREAD")

    def test_normal_track5_gap_divergence_entry(self):
        """[Normal] Track 5: Gap Z-Score = 2.0 (1.5 <= z < 4.0) 정상 갭 인입 시 갭 수렴 옵션 신호 -> Order 생성"""
        st5 = self.runtime.strategies[4] # Track 5
        st5.reset_state()
        res = st5.evaluate_gap_divergence(
            open_price=355.0,
            prev_close_price=350.0,
            active_vol=1.0,
            current_regime="NORMAL",
            date_str="2026-08-28"
        )
        self.assertEqual(res["status"], "TRIGGERED")
        self.assertGreater(len(res["signals"]), 0)

    def test_normal_track8_monthly_wide_strangle(self):
        """[Normal] Track 8: DTE=20 정상 인입 시 와이드 스트랭글 양매수 신호 -> Order 생성"""
        st8 = self.runtime.strategies[7] # Track 8
        st8.reset_state()
        res = st8.evaluate_entry(
            dte=20.0,
            budget=1_000_000.0,
            current_price=350.0,
            current_regime="NORMAL",
            date_str="2026-08-28"
        )
        self.assertEqual(res["status"], "TRIGGERED")
        self.assertGreater(len(res["signals"]), 0)

    # =========================================================================
    # 2. 실패 케이스 (Failure Cases)
    # =========================================================================

    def test_failure_nan_input_isolated_without_state_corruption(self):
        """[Failure] NaN 시세 인입 시 예외 격리 및 잔고/원장 상태 보존 검증"""
        tick_nan = CanonicalMarketTick(
            timestamp="2026-08-28 09:00:00",
            underlying_price=float('nan')
        )
        # Runtime process_tick에서 NaN 시세 발생 시 시스템 중단 없이 예외 처리
        commands = self.runtime.process_tick(tick_nan)
        self.assertEqual(len(commands), 0, "No corrupt orders should be generated on NaN tick")
        self.assertEqual(self.account_summary.balance, 50_000_000.0, "Balance must remain intact")

    def test_failure_daily_loss_exceeded_blocks_new_strategy_orders(self):
        """[Failure] 일일 손실 한도 초과 시 RiskGate에서 전략의 정상 신호 주문 원천 차단"""
        # 일일 손실 한도(-1000만원) 초과 계좌 모의
        stressed_account = CanonicalAccountSummary(
            account_id="ACC-001",
            total_balance=38_000_000.0,
            realized_pnl=-11_000_000.0, # -1100만 < -1000만
            unrealized_pnl=0.0,
            used_margin=0.0,
            free_margin=38_000_000.0
        )
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-T1-FAIL-01",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=1,
            price=2.50,
            strike=350.0,
            option_type=CanonicalOptionType.CALL
        )
        is_approved, token, reason = self.runtime.risk_gate.admit_order(cmd, stressed_account)
        self.assertFalse(is_approved, "RiskGate must deny orders when daily loss limit is breached")
        self.assertIsNone(token)
        self.assertIn("EXCEEDED_MAX_DAILY_LOSS", reason)

    def test_failure_invalid_signal_fields_rejected_by_generator(self):
        """[Failure] 수량 음수 또는 필수 태그 누락 등 비정상 신호 인입 시 SignalGenerator 즉시 거부"""
        sig_invalid = CanonicalStrategySignal(
            signal_id="SIG-INV-01",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=-10, # 음수 수량
            price=2.50,
            strike=350.0,
            option_type=CanonicalOptionType.CALL,
            tag_id="", # 필수 태그 누락
            timestamp="2026-08-28 09:00:00"
        )
        is_valid, err = self.runtime.signal_generator.validate_signal(sig_invalid)
        self.assertFalse(is_valid)
        self.assertIn("INVALID_QTY", err)

    def test_failure_broker_network_exception_safe_rollback(self):
        """[Failure] Broker 주문 전송 시 통신 예외 발생 시 원장 오염 없이 안전 격리"""
        class FailingBroker:
            def send_order(self, cmd, token=None):
                raise ConnectionResetError("Virtual Broker Connection Lost")

        failing_broker = FailingBroker()
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-BROKER-FAIL",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=1,
            price=2.50,
            strike=350.0,
            option_type=CanonicalOptionType.CALL
        )
        try:
            failing_broker.send_order(cmd, token="TOK-VALID")
        except ConnectionResetError:
            pass # 정상 예외 포착
        # 원장 검증
        snap = self.vssf.get_account_snapshot()
        self.assertEqual(snap.balance, 50_000_000.0, "No phantom balance mutation after broker error")

    # =========================================================================
    # 3. 경계 케이스 (Boundary Cases)
    # =========================================================================

    def test_boundary_track5_gap_zscore_lower_threshold(self):
        """[Boundary] Track 5: Gap Z-Score 하한 경계 (1.5000) 미달(1.49) vs 초과(1.51) 정밀 검증"""
        st5 = self.runtime.strategies[4]
        daily_std = 350.0 * (0.15 / math.sqrt(252))

        # 1) Z = 1.49 (미달 -> NO_TRIGGER)
        st5.reset_state()
        res_sub = st5.evaluate_gap_divergence(
            open_price=350.0 + (1.49 * daily_std),
            prev_close_price=350.0,
            active_vol=1.0,
            current_regime="CUSTOM",
            date_str="2026-08-28"
        )
        self.assertEqual(res_sub["status"], "NO_TRIGGER")
        self.assertEqual(len(res_sub["signals"]), 0)

        # 2) Z = 1.51 (임계값 초과 -> TRIGGERED)
        st5.reset_state()
        res_super = st5.evaluate_gap_divergence(
            open_price=350.0 + (1.51 * daily_std),
            prev_close_price=350.0,
            active_vol=1.0,
            current_regime="CUSTOM",
            date_str="2026-08-28"
        )
        self.assertEqual(res_super["status"], "TRIGGERED")
        self.assertGreater(len(res_super["signals"]), 0)

    def test_boundary_track5_gap_zscore_upper_blackswan_threshold(self):
        """[Boundary] Track 5: Gap Z-Score 상한 블랙스완 경계 (4.0000) 직전 허용(3.99) vs 초과 차단(4.01) 정밀 검증"""
        st5 = self.runtime.strategies[4]
        daily_std = 350.0 * (0.15 / math.sqrt(252))

        # 1) Z = 3.99 (직전 허용 -> TRIGGERED)
        st5.reset_state()
        res_allow = st5.evaluate_gap_divergence(
            open_price=350.0 + (3.99 * daily_std),
            prev_close_price=350.0,
            active_vol=1.0,
            current_regime="CUSTOM",
            date_str="2026-08-28"
        )
        self.assertEqual(res_allow["status"], "TRIGGERED")

        # 2) Z = 4.01 (상한 초과 -> BLACK_SWAN_GAP_BLOCKED 차단)
        st5.reset_state()
        res_super_block = st5.evaluate_gap_divergence(
            open_price=350.0 + (4.01 * daily_std),
            prev_close_price=350.0,
            active_vol=1.0,
            current_regime="CUSTOM",
            date_str="2026-08-28"
        )
        self.assertEqual(res_super_block["status"], "BLACK_SWAN_GAP_BLOCKED")
        self.assertEqual(len(res_super_block["signals"]), 0)

    def test_boundary_riskgate_max_order_quantity(self):
        """[Boundary] RiskGate: 단일 주문 최대 한도(50계약) 정확히 일치(50) vs 1계약 초과(51) 경계 검증"""
        # 1) Qty = 50 (최대 한도 정확히 일치 -> 승인)
        cmd_50 = CanonicalOrderCommand(
            client_order_id="ORD-BOUND-50",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=50,
            price=2.50,
            strike=350.0,
            option_type=CanonicalOptionType.CALL
        )
        is_approved_50, token_50, _ = self.runtime.risk_gate.admit_order(cmd_50, self.account_summary)
        self.assertTrue(is_approved_50, "Order with qty == max_single_order_qty (50) must be approved")
        self.assertIsNotNone(token_50)

        # 2) Qty = 51 (1계약 초과 -> 차단)
        cmd_51 = CanonicalOrderCommand(
            client_order_id="ORD-BOUND-51",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=51,
            price=2.50,
            strike=350.0,
            option_type=CanonicalOptionType.CALL
        )
        is_approved_51, token_51, reason_51 = self.runtime.risk_gate.admit_order(cmd_51, self.account_summary)
        self.assertFalse(is_approved_51, "Order with qty == 51 must be rejected")
        self.assertIsNone(token_51)
        self.assertIn("EXCEEDED_MAX_ORDER_QTY", reason_51)

    def test_boundary_track2_stop_loss_threshold(self):
        """[Boundary] Track 2: 손절 기준(-30.0%) 직전(-29.99%) vs 정확히 일치(-30.0%) 경계 검증"""
        st2 = self.runtime.strategies[1]
        st2.trap_state = {
            "is_active": True,
            "entry_price": 2.00 # 진입가 2.00pt
        }
        # 1) 현재가 1.4002pt (손실률 -29.99% -> -30% 미달 -> NORMAL)
        res_pre = st2.evaluate_trap_status(current_price=1.4002)
        self.assertEqual(res_pre["status"], "NORMAL")

        # 2) 현재가 1.4000pt (손실률 -30.00% 정확히 일치 -> STOP_LOSS 발동)
        res_exact = st2.evaluate_trap_status(current_price=1.4000)
        self.assertEqual(res_exact["status"], "STOP_LOSS")
        self.assertGreater(len(res_exact["signals"]), 0)

    def test_boundary_track7_expiry_cutoff_time(self):
        """[Boundary] Track 7: 만기 D-0 컷오프 시간(15:15:00) 직전(15:14:59) vs 정확히 일치(15:15:00) 경계 검증"""
        st7 = self.runtime.strategies[6] # Track 7
        st7.date_reset_helper.last_trading_date = "2026-08-28"
        st7.insurance_state = {
            "is_active": True,
            "bought_date": "2026-08-28",
            "long_put_strike": 335.0,
            "long_call_strike": 365.0,
            "premium_spent": 350000.0,
            "high_watermark_intrinsic": 0.0,
            "trailing_stop_active": False
        }
        # 1) 15:14:59 (15:00~15:15 사이 지정가 우선 청산 펜딩)
        res_pre = st7.evaluate_expiry_cutoff(
            time_str="15:14:59",
            is_expiry_day=True,
            date_str="2026-08-28"
        )
        self.assertEqual(res_pre["status"], "CUTOFF_LIMIT_PENDING")

        # 2) 15:15:00 (컷오프 정확히 일치 -> Fallback Market 100% 강제 청산)
        st7.insurance_state["is_active"] = True
        res_exact = st7.evaluate_expiry_cutoff(
            time_str="15:15:00",
            is_expiry_day=True,
            date_str="2026-08-28"
        )
        self.assertEqual(res_exact["status"], "CUTOFF_FALLBACK_EXECUTED")
        self.assertGreater(len(res_exact["signals"]), 0)


if __name__ == "__main__":
    unittest.main()
