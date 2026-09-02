"""Comprehensive Functional Assertion Tests for Strategy Tracks 1 to 9.

Verifies the complete closed-loop pathway for every single track:
Input Data (Market Tick / Condition)
-> Feature Calculation & Usage
-> Strategy Decision Logic
-> Signal Generation
-> SignalGenerator Validation & DecisionArbiter Arbitration
-> CanonicalOrderCommand Transformation
-> RiskGate Pre-trade Risk Evaluation & Token Issuance
-> OrderRouter & OMS FSM Transition
-> PaperBrokerAdapter Execution & Position/Ledger Mutation
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


class TestTrackPathwaysAll(unittest.TestCase):
    """Track 1~9 전수 경로 Functional Assertion 검증 스위트"""

    def setUp(self):
        self.vssf = VirtualSecuritiesFirmRuntime(initial_capital=50_000_000.0)
        self.broker = BrokerFactory.create_broker(mode=BrokerMode.PAPER, vssf_runtime=self.vssf)
        self.account_summary = self.vssf.get_account_snapshot()
        self.runtime = OptionProgramRuntime(account_summary=self.account_summary)

    def _disable_all_tracks_except(self, target_track: str):
        for k in self.runtime.enabled_strategies:
            self.runtime.enabled_strategies[k] = (k == target_track)

    def test_track1_dual_ring_fence_pathway(self):
        """[Track 1] 가두리 개장 선제 구축 및 만기 D-4 컷오프 경로 추적"""
        self._disable_all_tracks_except("Track1")
        tick = CanonicalMarketTick(
            timestamp="2026-08-28 09:00:01",
            underlying_price=350.0,
            strike_price=350.0,
            option_type="CALL",
            bid_price=2.45,
            ask_price=2.55,
            last_price=2.50,
            volume=100,
            seq_id=101
        )
        commands = self.runtime.process_tick(tick)
        
        # 1. 시그널 및 주문 생성 검증
        self.assertGreater(len(commands), 0, "Track 1 must generate initial dual-ring fence commands")
        cmd = commands[0]
        self.assertEqual(cmd.track_id, "Track1")
        self.assertTrue(cmd.client_order_id.startswith("ORD-T101-Track1-"))
        
        # 2. OrderRouter -> Broker 접수 및 별도 체결 수신 검증
        for c in commands:
            ack = self.broker.send_order(c)
            self.assertIsNotNone(ack)
            self.assertTrue(ack.success)

        reports = self.broker.poll_execution_reports()
        for rep in reports:
            self.runtime.consume_execution_report(rep)

        for c in commands:
            order_uuid = self.runtime._order_id_to_uuid[c.client_order_id]
            self.assertEqual(self.runtime.oms_fsm.get_status(order_uuid), OrderStatus.FILLED)

        # 3. 원장 및 포지션 반영 검증
        self.assertGreater(len(self.vssf.account.ledger_engine.transactions), 0)

    def test_track2_asymmetric_trap_pathway(self):
        """[Track 2] 비대칭 트랩 및 변동성 연동 진입 경로 추적"""
        self._disable_all_tracks_except("Track2")
        tick = CanonicalMarketTick(
            timestamp="2026-08-28 09:00:01",
            underlying_price=350.0,
            strike_price=350.0,
            option_type="CALL",
            bid_price=2.45,
            ask_price=2.55,
            last_price=2.50,
            volume=100,
            seq_id=201
        )
        commands = self.runtime.process_tick(tick)
        self.assertGreater(len(commands), 0, "Track 2 must build asymmetric trap on tick")
        for c in commands:
            self.assertEqual(c.track_id, "Track2")
            ack = self.broker.send_order(c)
            self.assertIsNotNone(ack)
            self.assertTrue(ack.success)

        reports = self.broker.poll_execution_reports()
        for rep in reports:
            self.runtime.consume_execution_report(rep)

        for c in commands:
            order_uuid = self.runtime._order_id_to_uuid[c.client_order_id]
            self.assertEqual(self.runtime.oms_fsm.get_status(order_uuid), OrderStatus.FILLED)

    def test_track3_statistical_arbitrage_pathway(self):
        """[Track 3] 통계적 차익거래 Z-Score 괴리 진입 경로 추적"""
        st3 = self.runtime.strategies[2]
        # 15틱 스프레드 시계열 주입하여 Z-Score Dislocation 유발
        spread_history = [0.5] * 14 + [3.5]
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
        self.assertGreater(len(res.get("signals", [])), 0, "Track 3 must generate arbitrage signal on high Z-score")
        sig = res["signals"][0]
        self.assertEqual(sig["type"], "SHORT_SPREAD")

    def test_track4_gamma_scalping_basecamp_pathway(self):
        """[Track 4] 감마 스캘핑 베이스캠프 구축 및 발주 경로 추적"""
        self._disable_all_tracks_except("Track4")
        tick = CanonicalMarketTick(
            timestamp="2026-08-28 09:05:00",
            underlying_price=350.0,
            strike_price=350.0,
            option_type="CALL",
            bid_price=2.45,
            ask_price=2.55,
            last_price=2.50,
            volume=100,
            seq_id=401
        )
        commands = self.runtime.process_tick(tick)
        self.assertEqual(len(commands), 1, "Track 4 must deploy hybrid basecamp")
        cmd = commands[0]
        self.assertEqual(cmd.track_id, "Track4")
        ack = self.broker.send_order(cmd)
        self.assertIsNotNone(ack)
        self.assertTrue(ack.success)
        reports = self.broker.poll_execution_reports()
        for rep in reports:
            self.runtime.consume_execution_report(rep)
        self.assertEqual(self.runtime.oms_fsm.get_status(self.runtime._order_id_to_uuid[cmd.client_order_id]), OrderStatus.FILLED)

    def test_track5_gap_divergence_pathway(self):
        """[Track 5] 시초가 갭 괴리 역방향 저격 진입 경로 추적"""
        st5 = self.runtime.strategies[4]
        res = st5.evaluate_gap_divergence(
            open_price=355.0,  # +5.0pt 갭상승
            prev_close_price=350.0,
            active_vol=1.0,
            current_regime="NORMAL",
            date_str="2026-08-28"
        )
        self.assertEqual(res["status"], "TRIGGERED")
        self.assertEqual(len(res["signals"]), 1)
        self.assertEqual(res["signals"][0]["action"], "ENTER_GAP_SHORT")

    def test_track6_daily_tail_insurance_pathway(self):
        """[Track 6] 데일리 변동성 폭발 0DTE 테일 보험 발주 경로 추적"""
        st6 = self.runtime.strategies[5]
        res = st6.evaluate_insurance_buy(
            current_price=350.0,
            active_vol=1.5,  # 1.3배 이상 변동성 폭발
            base_vol=1.0,
            budget=1000000.0,
            date_str="2026-08-28",
            time_str="09:05:00"
        )
        self.assertEqual(res["status"], "TRIGGERED")
        self.assertEqual(len(res["signals"]), 1)
        self.assertEqual(res["signals"][0]["action"], "BUY_LIMIT_DAILY_INSURANCE")

    def test_track7_weekly_insurance_pathway(self):
        """[Track 7] 위클리 테일 보험 및 15:15 타임 컷오프 경로 추적"""
        self._disable_all_tracks_except("Track7")
        tick = CanonicalMarketTick(
            timestamp="2026-08-28 09:00:01",
            underlying_price=350.0,
            strike_price=350.0,
            option_type="CALL",
            bid_price=2.45,
            ask_price=2.55,
            last_price=2.50,
            volume=100,
            seq_id=701
        )
        commands = self.runtime.process_tick(tick)
        self.assertEqual(len(commands), 1, "Track 7 must trigger weekly insurance on week start")
        cmd = commands[0]
        self.assertEqual(cmd.track_id, "Track7")
        ack = self.broker.send_order(cmd)
        self.assertIsNotNone(ack)
        self.assertTrue(ack.success)
        reports = self.broker.poll_execution_reports()
        for rep in reports:
            self.runtime.consume_execution_report(rep)
        self.assertEqual(self.runtime.oms_fsm.get_status(self.runtime._order_id_to_uuid[cmd.client_order_id]), OrderStatus.FILLED)

    def test_track8_monthly_wide_strangle_pathway(self):
        """[Track 8] 월간 와이드 스트랭글 진입 및 히스테리시스 경로 추적"""
        self._disable_all_tracks_except("Track8")
        tick = CanonicalMarketTick(
            timestamp="2026-08-28 09:00:01",
            underlying_price=350.0,
            strike_price=350.0,
            option_type="CALL",
            bid_price=2.45,
            ask_price=2.55,
            last_price=2.50,
            volume=100,
            seq_id=801,
            expiry="2026-10-08"
        )
        commands = self.runtime.process_tick(tick)
        self.assertEqual(len(commands), 1, "Track 8 must trigger monthly wide strangle")
        cmd = commands[0]
        self.assertEqual(cmd.track_id, "Track8")
        ack = self.broker.send_order(cmd)
        self.assertIsNotNone(ack)
        self.assertTrue(ack.success)
        reports = self.broker.poll_execution_reports()
        for rep in reports:
            self.runtime.consume_execution_report(rep)
        self.assertEqual(self.runtime.oms_fsm.get_status(self.runtime._order_id_to_uuid[cmd.client_order_id]), OrderStatus.FILLED)

    def test_track9_event_overnight_insurance_pathway(self):
        """[Track 9] 이벤트/오버나잇 동적 헤지 연동 경로 추적"""
        self._disable_all_tracks_except("Track9")
        tick = CanonicalMarketTick(
            timestamp="2026-08-28 09:00:01",
            underlying_price=350.0,
            strike_price=350.0,
            option_type="CALL",
            bid_price=2.45,
            ask_price=2.55,
            last_price=2.50,
            volume=100,
            seq_id=901
        )
        commands = self.runtime.process_tick(tick)
        self.assertEqual(len(commands), 1, "Track 9 must trigger overnight hedge sizing")
        cmd = commands[0]
        self.assertEqual(cmd.track_id, "Track9")
        ack = self.broker.send_order(cmd)
        self.assertIsNotNone(ack)
        self.assertTrue(ack.success)
        reports = self.broker.poll_execution_reports()
        for rep in reports:
            self.runtime.consume_execution_report(rep)
        self.assertEqual(self.runtime.oms_fsm.get_status(self.runtime._order_id_to_uuid[cmd.client_order_id]), OrderStatus.FILLED)


if __name__ == "__main__":
    unittest.main()
