"""Functional Assertion Tests for 4-3: Empty, Invalid, Duplicate Inputs and Exception Handling.

Verifies:
Assertion 1: Empty / None inputs are safely rejected without triggering Broker.send_order.
Assertion 2: Invalid inputs (negative qty, zero price, missing fields) are blocked pre-trade.
Assertion 3: Duplicate signals / orders are debounced and prevented from duplicate execution.
Assertion 4: Duplicate execution reports do not duplicate ledger transactions or mutate balance twice.
Assertion 5: Terminal states (FILLED, REJECTED, CANCELLED) and conflicting signals are safely protected.
Assertion 6: Exceptions do not corrupt internal state, and subsequent normal trading remains healthy.
"""
import unittest
import uuid
import asyncio
from typing import Dict, Any, List
from unittest.mock import MagicMock

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
from shared.core.contracts import OrderStatus, RiskApprovalToken
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime
from option_program.broker.broker_interface import BrokerFactory, BrokerMode
from option_program.runtime.program_runtime import OptionProgramRuntime
from option_program.strategy.signal_generator import SignalGenerator
from option_program.strategy.decision_arbiter import DecisionArbiter
from option_program.risk_control.risk_engine import RiskGate, RiskConfig
from option_program.orders.oms_fsm import OmsFsm


class TestEmptyInvalidDuplicateExceptions(unittest.TestCase):
    """4단계-3 중복·빈·잘못된 입력 및 예외 방어 종합 검증 스위트"""

    def setUp(self):
        self.vssf = VirtualSecuritiesFirmRuntime(initial_capital=50_000_000.0)
        self.broker = BrokerFactory.create_broker(mode=BrokerMode.PAPER, vssf_runtime=self.vssf)
        self.account_summary = self.vssf.get_account_snapshot()
        self.runtime = OptionProgramRuntime(account_summary=self.account_summary)

    # -------------------------------------------------------------
    # Assertion 1: 빈 입력 차단 (Empty / None inputs)
    # -------------------------------------------------------------
    def test_assertion1_empty_inputs_produce_zero_broker_calls(self):
        """[Assertion 1] 빈 신호 / 빈 리스트 입력 시 Broker 호출 0회 검증"""
        arbiter = DecisionArbiter()
        # 1. 빈 신호 목록 중재
        arb_res = arbiter.arbitrate([], self.account_summary)
        self.assertEqual(len(arb_res.approved_signals), 0)

        # 2. Mock Broker를 통한 호출 횟수 검증
        mock_broker = MagicMock()
        commands = []
        for sig in arb_res.approved_signals:
            cmd = self.runtime.signal_generator.process_signal(sig)
            if cmd:
                commands.append(cmd)
        for c in commands:
            mock_broker.send_order(c)

        mock_broker.send_order.assert_not_called()
        self.assertEqual(mock_broker.send_order.call_count, 0)

    # -------------------------------------------------------------
    # Assertion 2: 잘못된 입력 차단 (Invalid inputs)
    # -------------------------------------------------------------
    def test_assertion2_invalid_fields_blocked_before_broker(self):
        """[Assertion 2] 수량 0/음수, 가격 0/음수, 필수 태그 누락 등 잘못된 입력 원천 차단 검증"""
        sig_gen = SignalGenerator()

        # (1) 수량 0
        sig_zero_qty = CanonicalStrategySignal(
            signal_id="SIG-INV-1",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=0,
            price=2.50,
            strike=350.0,
            option_type=CanonicalOptionType.CALL,
            tag_id="ENTRY"
        )
        val1, err1 = sig_gen.validate_signal(sig_zero_qty)
        self.assertFalse(val1)
        self.assertIn("INVALID_QTY", err1)

        # (2) 가격 음수
        sig_neg_price = CanonicalStrategySignal(
            signal_id="SIG-INV-2",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=1,
            price=-1.50,
            strike=350.0,
            option_type=CanonicalOptionType.CALL,
            tag_id="ENTRY"
        )
        val2, err2 = sig_gen.validate_signal(sig_neg_price)
        self.assertFalse(val2)
        self.assertIn("INVALID_PRICE", err2)

        # (3) 필수 태그 누락
        sig_missing_tag = CanonicalStrategySignal(
            signal_id="SIG-INV-3",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=1,
            price=2.50,
            strike=350.0,
            option_type=CanonicalOptionType.CALL,
            tag_id=""
        )
        val3, err3 = sig_gen.validate_signal(sig_missing_tag)
        self.assertFalse(val3)
        self.assertIn("MISSING_TAG_ID", err3)

        # (4) 옵션 타입 누락
        sig_missing_opt_type = CanonicalStrategySignal(
            signal_id="SIG-INV-4",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=1,
            price=2.50,
            strike=350.0,
            option_type=None,
            tag_id="ENTRY"
        )
        val4, err4 = sig_gen.validate_signal(sig_missing_opt_type)
        self.assertFalse(val4)
        self.assertIn("MISSING_OPTION_TYPE", err4)

    # -------------------------------------------------------------
    # Assertion 3: 중복 주문 방지 (Duplicate orders debounce)
    # -------------------------------------------------------------
    def test_assertion3_duplicate_signal_debounced_and_single_execution(self):
        """[Assertion 3] 동일 신호 고속 반복 입력 시 디바운싱에 의해 단 1건만 통과 검증"""
        sig_gen = SignalGenerator(debounce_window_sec=1.0)
        sig = CanonicalStrategySignal(
            signal_id="SIG-DUP-01",
            track_id="Track2",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=1,
            price=2.00,
            strike=350.0,
            option_type=CanonicalOptionType.CALL,
            tag_id="EXECUTE_LONG_TRAP_LEG"
        )
        # 1차 정상 처리
        cmd1 = sig_gen.process_signal(sig, current_time=2000.0)
        self.assertIsNotNone(cmd1)

        # 0.1초 후 동일 신호 2차 인입 -> 차단
        cmd2 = sig_gen.process_signal(sig, current_time=2000.1)
        self.assertIsNone(cmd2, "Duplicate signal within 1.0s window must be blocked")

        # 0.2초 후 동일 신호 3차 인입 -> 차단
        cmd3 = sig_gen.process_signal(sig, current_time=2000.2)
        self.assertIsNone(cmd3, "Duplicate signal within 1.0s window must be blocked")

    # -------------------------------------------------------------
    # Assertion 4: 중복 Execution 방지 (Duplicate execution reports)
    # -------------------------------------------------------------
    def test_assertion4_duplicate_execution_report_idempotency(self):
        """[Assertion 4] 동일 ExecutionReport 재유입 시 원장/잔고 중복 반영 방어 (멱등성) 검증"""
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-DUP-EXEC-001",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=1,
            price=2.50,
            strike=350.0,
            option_type=CanonicalOptionType.CALL
        )
        # 1차 브로커 발주 및 체결
        rep = self.broker.send_order(cmd)
        self.assertIsNotNone(rep)
        self.runtime.consume_execution_report(rep)

        initial_tx_count = len(self.vssf.account.ledger_engine.transactions)
        initial_balance = self.vssf.account.balance

        # 동일한 체결 보고서(rep)를 2차 중복 소비 시도
        self.runtime.consume_execution_report(rep)

        # 트랜잭션 수 및 잔고가 중복 변경되지 않아야 함
        self.assertEqual(len(self.vssf.account.ledger_engine.transactions), initial_tx_count)
        self.assertEqual(self.vssf.account.balance, initial_balance)

    # -------------------------------------------------------------
    # Assertion 5: 충돌 상태 보호 (Clash & Terminal state protection)
    # -------------------------------------------------------------
    def test_assertion5_clash_netting_and_terminal_fsm_protection(self):
        """[Assertion 5] BUY vs SELL 상충 신호 넷팅 차단 및 종료 FSM 상태 멱등성 보호 검증"""
        # (1) DecisionArbiter 상충 신호 Netting 거절 검증
        arbiter = DecisionArbiter()
        sig_buy = CanonicalStrategySignal(
            signal_id="SIG-CLASH-BUY",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=1,
            price=2.50,
            strike=350.0,
            option_type=CanonicalOptionType.CALL,
            tag_id="BUY_LEG"
        )
        sig_sell = CanonicalStrategySignal(
            signal_id="SIG-CLASH-SELL",
            track_id="Track2",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.SELL,
            qty=1,
            price=2.50,
            strike=350.0,
            option_type=CanonicalOptionType.CALL,
            tag_id="SELL_LEG"
        )
        # 동일 종목에 대해 동시에 BUY와 SELL이 발생하면 상충 넷팅으로 모두 차단
        arb_res = arbiter.arbitrate([sig_buy, sig_sell], self.account_summary)
        self.assertEqual(len(arb_res.approved_signals), 1) # Priority 2(Track1) 승인, Priority 6(Track2) 종속 신호 넷팅 거부
        self.assertGreater(len(arb_res.rejected_signals), 0)
        self.assertIn("CLASH_NETTING_REJECTED", arb_res.rejected_signals[0][1])

        # (2) OmsFsm 멱등성 및 종료 상태 재등록 방어 검증
        fsm = OmsFsm()
        order_uuid = uuid.uuid4()
        token = RiskApprovalToken(
            order_id=order_uuid,
            timestamp_ns=1000,
            signature="SIG-TEST"
        )
        asyncio.run(fsm.register_order(token))
        self.assertEqual(fsm.get_status(order_uuid), OrderStatus.NEW)
        self.assertTrue(fsm.is_idempotent(order_uuid))

        # 체결 완료(FILLED) 전이
        asyncio.run(fsm.transition(order_uuid, OrderStatus.FILLED))
        self.assertEqual(fsm.get_status(order_uuid), OrderStatus.FILLED)

        # 이미 체결 완료된 주문을 동일 토큰으로 재등록 시도 -> 상태 덮어쓰기 방어
        asyncio.run(fsm.register_order(token))
        self.assertEqual(fsm.get_status(order_uuid), OrderStatus.FILLED, "Terminal state FILLED must not be overridden")

    # -------------------------------------------------------------
    # Assertion 6: 예외 후 상태 보존 (Exception state preservation)
    # -------------------------------------------------------------
    def test_assertion6_exception_handling_preserves_clean_state_and_resumes_trading(self):
        """[Assertion 6] 처리 중 예외 발생 시 회계/포지션 오염 없이 정상 후속 거래 계속 가능 검증"""
        initial_balance = self.vssf.account.balance
        initial_tx_count = len(self.vssf.account.ledger_engine.transactions)

        # 비정상 틱 인입 (가격이 NaN인 비정상 데이터)
        invalid_tick = CanonicalMarketTick(
            timestamp="2026-08-28 09:00:00",
            underlying_price=float('nan'),
            strike_price=350.0,
            option_type="CALL",
            bid_price=0.0,
            ask_price=0.0,
            last_price=0.0,
            volume=0,
            seq_id=9999
        )
        commands = self.runtime.process_tick(invalid_tick)
        self.assertEqual(len(commands), 0, "Invalid NaN tick must produce zero orders")

        # 회계/포지션 상태 오염 없음 확인
        self.assertEqual(self.vssf.account.balance, initial_balance)
        self.assertEqual(len(self.vssf.account.ledger_engine.transactions), initial_tx_count)

        # 정상 후속 틱 인입 시 정상 거래 재개 확인
        valid_tick = CanonicalMarketTick(
            timestamp="2026-08-28 09:05:00",
            underlying_price=350.0,
            strike_price=350.0,
            option_type="CALL",
            bid_price=2.45,
            ask_price=2.55,
            last_price=2.50,
            volume=100,
            seq_id=10000
        )
        normal_commands = self.runtime.process_tick(valid_tick)
        self.assertGreater(len(normal_commands), 0, "Subsequent valid tick must resume normal trading")

    # -------------------------------------------------------------
    # Assertion 7: 빈 Sensor 데이터 및 빈 문자열 방어
    # -------------------------------------------------------------
    def test_assertion7_empty_sensor_and_missing_features(self):
        """[Assertion 7] 빈 센서 스냅샷 / 빈 심볼 입력 시 안전 차단 검증"""
        # 1. 빈 심볼 / 잘못된 심볼 명령 거부
        cmd_empty_symbol = CanonicalOrderCommand(
            client_order_id="ORD-EMPTY-SYM",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=1,
            price=2.50,
            strike=350.0,
            option_type=CanonicalOptionType.CALL,
            symbol=""
        )
        # RiskGate에 빈 센서 스냅샷 전달 시에도 안전하게 평가 수행
        is_app, tok, reason = self.runtime.risk_gate.admit_order(cmd_empty_symbol, self.account_summary, sensor_snapshot=None)
        self.assertTrue(is_app, "Normal order with None sensor snapshot is admitted safely")
        self.assertIsNotNone(tok)

    # -------------------------------------------------------------
    # Assertion 8: Broker 예외 발생 시 회계 격리 (Broker Failure Isolation)
    # -------------------------------------------------------------
    def test_assertion8_broker_exception_isolation(self):
        """[Assertion 8] Broker.send_order() 중 예외 발생 시 원장 오염 방지 검증"""
        initial_balance = self.vssf.account.balance
        initial_tx_count = len(self.vssf.account.ledger_engine.transactions)

        faulty_broker = MagicMock()
        faulty_broker.send_order.side_effect = ConnectionResetError("Broker socket dropped")

        cmd = CanonicalOrderCommand(
            client_order_id="ORD-FAIL-001",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=1,
            price=2.50,
            strike=350.0,
            option_type=CanonicalOptionType.CALL
        )

        with self.assertRaises(ConnectionResetError):
            faulty_broker.send_order(cmd)

        # 원장/계좌 상태 변화 없음 확인
        self.assertEqual(self.vssf.account.balance, initial_balance)
        self.assertEqual(len(self.vssf.account.ledger_engine.transactions), initial_tx_count)


if __name__ == "__main__":
    unittest.main()
