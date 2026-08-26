"""E2E Test: Broker Results (FILLED / PARTIAL / REJECTED / CANCEL) -> Position -> PnL Consistency.

Verifies:
1. FILLED: Full execution reflects exact position mutation, realized PnL on close, margin sync.
2. PARTIAL: Partial execution reflects partial position mutation and partial PnL.
3. REJECTED: Broker rejection leaves position, balance, and PnL completely untouched (zero mutation).
4. CANCEL: Order cancellation transitions FSM to CANCELLED with zero position/PnL mutation.
5. End-to-End state consistency between Broker ExecutionReports, PositionManager, and PnLEngine.
"""
import sys
import time
import unittest
import uuid
from unittest.mock import MagicMock
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
from shared.core.contracts import OrderStatus, RiskApprovalToken  # noqa: E402
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime  # noqa: E402
from option_program.risk_control.risk_engine import RiskConfig, RiskEngine, RiskGate  # noqa: E402
from option_program.orders.order_router import OrderRouter  # noqa: E402
from option_program.orders.oms_fsm import OmsFsm  # noqa: E402
from option_program.broker.broker_interface import BrokerFactory, BrokerMode, IBrokerAdapter  # noqa: E402


class TestBrokerResultsPositionPnLE2E(unittest.TestCase):
    """Broker 결과(FILLED/PARTIAL/REJECTED/CANCEL) -> Position -> PnL 일관성 E2E 검증."""

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
        self.risk_engine = RiskEngine(config=self.risk_config)
        self.risk_gate = RiskGate(risk_engine=self.risk_engine)
        self.fsm = OmsFsm()
        self.router = OrderRouter(fsm=self.fsm)

        # 초기 틱 시세 주입 (옵션 기준가 2.5)
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
        self.account_snapshot = self.vssf.get_account_snapshot()
        self.inst_key = "KOSPI200_OPTION_2026-09_CALL_350.0"

    # =========================================================================
    # 1. FILLED (전량 체결) -> Position -> PnL 검증
    # =========================================================================

    def test_01_filled_entry_and_profit_close_updates_position_and_pnl(self):
        """[FILLED] 신규 매수 10계약 체결 -> 매도 10계약 익절 체결 시 실현 손익 및 포지션 제거 검증."""
        # 1. 신규 진입 매수 10계약 @ 2.5
        cmd_buy = CanonicalOrderCommand(
            client_order_id="ORD-FILLED-BUY", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            qty=10, price=2.5, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )
        _, token_buy, _ = self.risk_gate.admit_order(cmd_buy, self.account_snapshot, self.vssf.account.get_positions())
        oid_buy = self.router.register_and_route(cmd_buy, token_buy, self.broker)

        self.assertIsNotNone(oid_buy)
        self.assertEqual(self.fsm.get_status(oid_buy), OrderStatus.FILLED)

        # 포지션 확인: LONG 10 @ 체결가
        pos = self.vssf.account.get_positions()
        self.assertIn(self.inst_key, pos)
        self.assertEqual(pos[self.inst_key]["qty"], 10)
        buy_avg_price = pos[self.inst_key]["avg_price"]
        self.assertGreater(buy_avg_price, 0.0)
        self.assertEqual(pos[self.inst_key]["side"], "BUY")
        self.assertEqual(self.vssf.account.realized_pnl, 0.0)

        # 2. 전량 청산 매도 10계약 @ 3.0
        self.vssf.process_market_data(CanonicalMarketTick(
            timestamp="2026-08-23 09:05:00.000", underlying_price=3.0, bid_price=2.95, ask_price=3.05, last_price=3.0, seq_id=2
        ))
        cmd_sell = CanonicalOrderCommand(
            client_order_id="ORD-FILLED-SELL", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.SELL,
            qty=10, price=3.0, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )
        _, token_sell, _ = self.risk_gate.admit_order(cmd_sell, self.vssf.get_account_snapshot(), self.vssf.account.get_positions())
        oid_sell = self.router.register_and_route(cmd_sell, token_sell, self.broker)

        self.assertIsNotNone(oid_sell)
        self.assertEqual(self.fsm.get_status(oid_sell), OrderStatus.FILLED)

        # 포지션 확인: FLAT (0 또는 제거)
        pos_after = self.vssf.account.get_positions()
        self.assertTrue(self.inst_key not in pos_after or pos_after[self.inst_key]["qty"] == 0)

        # 실현 손익 확인
        sell_rep = self.vssf.execution_engine.reports[-1]
        expected_pnl = round((sell_rep.executed_price - buy_avg_price) * 10 * 250000.0, 2)
        self.assertAlmostEqual(self.vssf.account.realized_pnl, expected_pnl, places=2)
        summary = self.vssf.account.get_canonical_summary()
        self.assertEqual(summary.realized_pnl, expected_pnl)
        self.assertEqual(summary.used_margin, 0.0)



    # =========================================================================
    # 2. PARTIAL (부분 체결) -> Position -> PnL 검증
    # =========================================================================

    def test_02_partial_execution_reflects_partial_position_and_pnl(self):
        """[PARTIAL] 10계약 주문 중 4계약 부분체결 -> FSM PARTIAL, 포지션 4계약, 이후 청산 검증."""
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-PARTIAL-BUY", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            qty=10, price=2.5, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )
        _, token, _ = self.risk_gate.admit_order(cmd, self.account_snapshot, self.vssf.account.get_positions())

        # 4계약만 체결하는 Mock Broker
        mock_broker = MagicMock(spec=IBrokerAdapter)
        mock_broker.send_order.return_value = CanonicalExecutionReport(
            exec_id="EXEC-PART-1", client_order_id=cmd.client_order_id, track_id=cmd.track_id,
            asset_type=cmd.asset_type, side=cmd.side, executed_qty=4, executed_price=2.5,
            fee=400.0, slippage=0.0, timestamp="2026-08-23 09:00:00",
            symbol=cmd.symbol, option_type=cmd.option_type, strike=cmd.strike, expiry=cmd.expiry
        )

        oid = self.router.register_and_route(cmd, token, mock_broker)
        self.assertIsNotNone(oid)
        # FSM 상태가 PARTIAL로 반영됨을 확인
        self.assertEqual(self.fsm.get_status(oid), OrderStatus.PARTIAL)

        # 수신된 체결 리포트를 계좌에 반영
        self.vssf.account.apply_execution(mock_broker.send_order.return_value)

        # 계좌 포지션이 정확히 4계약만 반영되었는지 확인
        pos = self.vssf.account.get_positions()
        self.assertIn(self.inst_key, pos)
        self.assertEqual(pos[self.inst_key]["qty"], 4)
        self.assertEqual(pos[self.inst_key]["avg_price"], 2.5)

        # 잔여 포지션 중 2계약 부분 매도 청산 @ 3.0
        rep_partial_close = CanonicalExecutionReport(
            exec_id="EXEC-PART-CLOSE", client_order_id="ORD-PARTIAL-CLOSE", track_id="Track1",
            asset_type=cmd.asset_type, side=CanonicalOrderSide.SELL, executed_qty=2, executed_price=3.0,
            fee=200.0, slippage=0.0, timestamp="2026-08-23 09:02:00",
            symbol=cmd.symbol, option_type=cmd.option_type, strike=cmd.strike, expiry=cmd.expiry
        )
        self.vssf.account.apply_execution(rep_partial_close)

        # 포지션 잔여: 2계약 (4 - 2)
        pos_after_close = self.vssf.account.get_positions()
        self.assertEqual(pos_after_close[self.inst_key]["qty"], 2)
        # 실현 손익: 2계약 * 0.5 * 250,000 = 250,000 KRW
        self.assertEqual(self.vssf.account.realized_pnl, 250000.0)

    # =========================================================================
    # 3. REJECTED (주문 거부 / 실패) -> Position / PnL 무변화 검증
    # =========================================================================

    def test_03_rejected_order_leaves_position_and_pnl_completely_unchanged(self):
        """[REJECTED] Broker 거부/실패 시 FSM REJECTED, 포지션/손익/잔고 100% 무변동 검증."""
        # 기존 포지션 사전 생성: 5계약 @ 2.5
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-INIT-POS", client_order_id="ORD-INIT-POS", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY, executed_qty=5, executed_price=2.5,
            fee=500.0, slippage=0.0, timestamp="2026-08-23 09:00:00",
            symbol="KOSPI200", option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))

        snapshot_before = self.vssf.account.get_canonical_summary()
        pos_before = dict(self.vssf.account.get_positions()[self.inst_key])

        # 추가 주문 발주 -> Broker에서 거부(None)
        cmd_fail = CanonicalOrderCommand(
            client_order_id="ORD-FAIL-1", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            qty=10, price=2.5, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )
        _, token, _ = self.risk_gate.admit_order(cmd_fail, self.vssf.get_account_snapshot(), self.vssf.account.get_positions())

        failing_broker = MagicMock(spec=IBrokerAdapter)
        failing_broker.send_order.return_value = None

        oid = self.router.register_and_route(cmd_fail, token, failing_broker)
        self.assertIsNotNone(oid)
        self.assertEqual(self.fsm.get_status(oid), OrderStatus.REJECTED)

        # 상태 불변 검증
        snapshot_after = self.vssf.account.get_canonical_summary()
        pos_after = self.vssf.account.get_positions()[self.inst_key]

        self.assertEqual(pos_before["qty"], pos_after["qty"])
        self.assertEqual(pos_before["avg_price"], pos_after["avg_price"])
        self.assertEqual(snapshot_before.realized_pnl, snapshot_after.realized_pnl)
        self.assertEqual(snapshot_before.total_balance, snapshot_after.total_balance)
        self.assertEqual(snapshot_before.free_margin, snapshot_after.free_margin)

    # =========================================================================
    # 4. CANCEL (주문 취소) -> Position / PnL 무변화 검증
    # =========================================================================

    def test_04_cancelled_order_cleans_fsm_with_zero_position_mutation(self):
        """[CANCEL] 지연 미체결 주문 취소 -> FSM CANCELLED, 포지션/손익 무변동 확인."""
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-CANCEL-1", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            qty=10, price=2.5, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )
        _, token, _ = self.risk_gate.admit_order(cmd, self.account_snapshot, self.vssf.account.get_positions())

        # broker_adapter 없이 큐잉 모드로 라우팅 -> SENT 유지
        oid = self.router.register_and_route(cmd, token, broker_adapter=None)
        self.assertEqual(self.fsm.get_status(oid), OrderStatus.SENT)
        self.assertIn(oid, self.router._active_orders)

        # 30초 초과 지연 주문 스캔
        stale_orders = self.router.scan_stale_orders(current_time=time.time() + 35.0)
        self.assertIn(oid, stale_orders)

        # 주문 취소 실행
        cancelled = self.router.cancel_stale_order(oid)
        self.assertTrue(cancelled)
        self.assertEqual(self.fsm.get_status(oid), OrderStatus.CANCELLED)
        self.assertNotIn(oid, self.router._active_orders)

        # 포지션 및 손익 무변화 확인
        self.assertEqual(len(self.vssf.account.get_positions()), 0)
        self.assertEqual(self.vssf.account.realized_pnl, 0.0)

    def test_04b_stale_cancel_dispatches_real_broker_cancel_order_and_transitions_fsm(self):
        """[STALE CANCEL -> BROKER] Stale 감지 시 Broker.cancel_order() 실제 호출(1회, 정확한 order_id) 및 FSM CANCELLED 확인."""
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-STALE-BROKER-SUCCESS", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            qty=10, price=2.5, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )
        _, token, _ = self.risk_gate.admit_order(cmd, self.account_snapshot, self.vssf.account.get_positions())

        # Broker Mock 생성 (cancel_order 성공 반환)
        mock_broker = MagicMock(spec=IBrokerAdapter)
        mock_broker.cancel_order.return_value = True

        # 주문 라우팅 (대기 큐잉 상태 등록)
        oid = self.router.register_and_route(cmd, token, broker_adapter=None)
        self.assertIsNotNone(oid)
        self.assertEqual(self.fsm.get_status(oid), OrderStatus.SENT)
        self.assertIn(oid, self.router._active_orders)

        # 30초 초과 Stale 감지
        stale_orders = self.router.scan_stale_orders(current_time=time.time() + 35.0)
        self.assertIn(oid, stale_orders)

        # Stale 주문 취소 실행 -> 실제 Broker.cancel_order() 호출 검증
        cancelled = self.router.cancel_stale_order(oid, broker_adapter=mock_broker)

        # 1. 취소 결과 성공 확인
        self.assertTrue(cancelled)
        # 2. Broker.cancel_order()가 정확히 1회 호출되었는지 확인
        self.assertEqual(mock_broker.cancel_order.call_count, 1)
        # 3. 올바른 client_order_id가 전달되었는지 확인
        mock_broker.cancel_order.assert_called_once_with("ORD-STALE-BROKER-SUCCESS")
        # 4. FSM 상태가 CANCELLED로 정상 전이되었는지 확인
        self.assertEqual(self.fsm.get_status(oid), OrderStatus.CANCELLED)
        # 5. _active_orders에서 order_id가 안전하게 제거되었는지 확인
        self.assertNotIn(oid, self.router._active_orders)
        self.assertNotIn(oid, self.router._order_brokers)

    def test_04c_stale_cancel_broker_failure_and_exception_handling(self):
        """[STALE CANCEL -> BROKER FAIL] Broker cancel_order() 실패 또는 예외 시 FSM CANCELLED 전이 차단 및 활성 주문 유지 확인."""
        # 1. Broker cancel_order()가 False(실패)를 반환하는 경우
        cmd_fail = CanonicalOrderCommand(
            client_order_id="ORD-STALE-BROKER-FAIL", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            qty=10, price=2.5, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )
        _, token_fail, _ = self.risk_gate.admit_order(cmd_fail, self.account_snapshot, self.vssf.account.get_positions())
        mock_broker_fail = MagicMock(spec=IBrokerAdapter)
        mock_broker_fail.cancel_order.return_value = False  # 취소 실패

        oid_fail = self.router.register_and_route(cmd_fail, token_fail, broker_adapter=None)
        cancelled_fail = self.router.cancel_stale_order(oid_fail, broker_adapter=mock_broker_fail)

        self.assertFalse(cancelled_fail)
        mock_broker_fail.cancel_order.assert_called_once_with("ORD-STALE-BROKER-FAIL")
        # 실패 시 CANCELLED로 전이되지 않고 기존 SENT 상태 유지
        self.assertNotEqual(self.fsm.get_status(oid_fail), OrderStatus.CANCELLED)
        self.assertEqual(self.fsm.get_status(oid_fail), OrderStatus.SENT)
        self.assertIn(oid_fail, self.router._active_orders)

        # 2. Broker cancel_order() 실행 중 Exception이 발생하는 경우
        cmd_exc = CanonicalOrderCommand(
            client_order_id="ORD-STALE-BROKER-EXC", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            qty=10, price=2.5, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )
        _, token_exc, _ = self.risk_gate.admit_order(cmd_exc, self.account_snapshot, self.vssf.account.get_positions())
        mock_broker_exc = MagicMock(spec=IBrokerAdapter)
        mock_broker_exc.cancel_order.side_effect = RuntimeError("Broker Network Timeout")

        oid_exc = self.router.register_and_route(cmd_exc, token_exc, broker_adapter=None)
        cancelled_exc = self.router.cancel_stale_order(oid_exc, broker_adapter=mock_broker_exc)

        self.assertFalse(cancelled_exc)
        mock_broker_exc.cancel_order.assert_called_once_with("ORD-STALE-BROKER-EXC")
        self.assertNotEqual(self.fsm.get_status(oid_exc), OrderStatus.CANCELLED)
        self.assertEqual(self.fsm.get_status(oid_exc), OrderStatus.SENT)
        self.assertIn(oid_exc, self.router._active_orders)

    # =========================================================================
    # 5. Mark-to-Market 실시간 미실현 손익 동기화 검증
    # =========================================================================

    def test_05_mark_to_market_unrealized_pnl_sync_across_ticks(self):
        """[Mark-to-Market] 체결 후 틱 시세 변동에 따른 Unrealized PnL 실시간 정합성 검증."""
        # 1. 매수 10계약 @ 2.5 체결
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-M2M-BUY", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            qty=10, price=2.5, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )
        _, token, _ = self.risk_gate.admit_order(cmd, self.account_snapshot, self.vssf.account.get_positions())
        self.router.register_and_route(cmd, token, self.broker)

        # 체결 평단가 확인
        pos = self.vssf.account.get_positions()
        buy_avg_price = pos[self.inst_key]["avg_price"]

        # 체결 직후 미실현 손익: (base_tick_price 2.5 - buy_avg_price) * 10 * 250000.0
        init_expected_unrealized = round((2.5 - buy_avg_price) * 10 * 250000.0, 2)
        self.assertEqual(self.vssf.account.unrealized_pnl, init_expected_unrealized)


        # 2. 시세 상승: 2.8로 변동 -> (2.8 - buy_avg_price) * 10 * 250,000 KRW
        self.vssf.process_market_data(CanonicalMarketTick(
            timestamp="2026-08-23 09:01:00.000", underlying_price=2.8, seq_id=10
        ))
        expected_up = round((2.8 - buy_avg_price) * 10 * 250000.0, 2)
        self.assertEqual(self.vssf.account.unrealized_pnl, expected_up)
        summary_up = self.vssf.account.get_canonical_summary()
        self.assertEqual(summary_up.unrealized_pnl, expected_up)

        # 3. 시세 하락: 2.2로 변동 -> (2.2 - buy_avg_price) * 10 * 250,000 KRW
        self.vssf.process_market_data(CanonicalMarketTick(
            timestamp="2026-08-23 09:02:00.000", underlying_price=2.2, seq_id=11
        ))
        expected_down = round((2.2 - buy_avg_price) * 10 * 250000.0, 2)
        self.assertEqual(self.vssf.account.unrealized_pnl, expected_down)
        summary_down = self.vssf.account.get_canonical_summary()
        self.assertEqual(summary_down.unrealized_pnl, expected_down)



if __name__ == "__main__":
    unittest.main()
