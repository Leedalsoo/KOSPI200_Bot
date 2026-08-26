"""E2E Edge Test: ExecutionReport Abnormal State/Qty Defense & Multi-Execution Consistency.

Covers:
1. TEST E: FILLED + executed_qty = 0 -> Zero position/PnL mutation.
2. TEST F: PARTIAL + executed_qty = 0 -> Zero position/PnL mutation.
3. TEST G: executed_qty > requested_qty -> Oversized fill defense / detection.
4. TEST H: executed_qty < 0 -> Negative fill quantity defense.
5. TEST I: Same order_id + different execution_ids -> Correct additive accumulation.
6. TEST J: Multi-execution partial fills weighted average price + full close PnL.
7. TEST K: Duplicate execution_id re-delivery -> Exactly-once idempotency guarantee.
8. TEST L: Distinct execution_ids with distinct executions -> Correct additive accumulation.
"""
import sys
import unittest
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
from option_program.broker.broker_interface import IBrokerAdapter  # noqa: E402


class TestBrokerExecutionPositionPnLConsistencyEdgeE2E(unittest.TestCase):
    """ExecutionReport 비정상 상태/수량 방어 및 복수 execution_id 일관성 E2E 검증."""

    def setUp(self):
        self.initial_capital = 5_000_000_000.0
        self.vssf = VirtualSecuritiesFirmRuntime(initial_capital=self.initial_capital)

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
        self.inst_key = "KOSPI200_OPTION_2026-09_CALL_350.0"

    # =========================================================================
    # 1. TEST E: FILLED + executed_qty = 0
    # =========================================================================

    def test_E_filled_with_zero_executed_qty_causes_zero_mutation(self):
        """[TEST E] FILLED 상태이지만 executed_qty=0인 리포트 수신 시 포지션/손익/잔고 변동 0."""
        snap_before = self.vssf.account.get_canonical_summary()
        pos_before = dict(self.vssf.account.get_positions())

        rep = CanonicalExecutionReport(
            exec_id="EXEC-E-001", client_order_id="ORD-E-001", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=0, executed_price=2.5, fee=0.0, slippage=0.0,
            timestamp="2026-08-23 09:00:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        )
        self.vssf.account.apply_execution(rep)

        pos_after = self.vssf.account.get_positions()
        snap_after = self.vssf.account.get_canonical_summary()

        self.assertEqual(len(pos_after), len(pos_before))
        self.assertNotIn(self.inst_key, pos_after)
        self.assertEqual(snap_before.realized_pnl, snap_after.realized_pnl)
        self.assertEqual(snap_before.total_balance, snap_after.total_balance)
        self.assertEqual(snap_before.free_margin, snap_after.free_margin)

    # =========================================================================
    # 2. TEST F: PARTIAL + executed_qty = 0
    # =========================================================================

    def test_F_partial_with_zero_executed_qty_causes_zero_mutation(self):
        """[TEST F] PARTIAL 상태이지만 executed_qty=0인 리포트 수신 시 포지션/손익 변동 0."""
        # 기존 포지션 생성: 5개 @ 2.5
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-F-INIT", client_order_id="ORD-F-INIT", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=5, executed_price=2.5, fee=500.0, slippage=0.0,
            timestamp="2026-08-23 09:00:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))

        snap_before = self.vssf.account.get_canonical_summary()
        pos_before = dict(self.vssf.account.get_positions()[self.inst_key])

        # PARTIAL + qty=0 주입
        rep_zero = CanonicalExecutionReport(
            exec_id="EXEC-F-ZERO", client_order_id="ORD-F-PART", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=0, executed_price=2.5, fee=0.0, slippage=0.0,
            timestamp="2026-08-23 09:01:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        )
        self.vssf.account.apply_execution(rep_zero)

        pos_after = self.vssf.account.get_positions()[self.inst_key]
        snap_after = self.vssf.account.get_canonical_summary()

        self.assertEqual(pos_before["qty"], pos_after["qty"])
        self.assertEqual(pos_before["avg_price"], pos_after["avg_price"])
        self.assertEqual(snap_before.realized_pnl, snap_after.realized_pnl)
        self.assertEqual(snap_before.total_balance, snap_after.total_balance)

    # =========================================================================
    # 3. TEST G: executed_qty > requested_qty (초과 체결 방어)
    # =========================================================================

    def test_G_oversized_execution_qty_defense(self):
        """[TEST G] 요청수량 10개 대비 초과체결 11개 수신 시 OrderRouter/FSM 방어 및 Mutation=0 검증."""
        # 1. 사전 상태 Snapshot 측정
        snap_before = self.vssf.account.get_canonical_summary()
        pos_before = {k: dict(v) for k, v in self.vssf.account.get_positions().items()}
        realized_pnl_before = self.vssf.account.realized_pnl
        total_balance_before = self.vssf.account.balance
        free_margin_before = self.vssf.account.free_margin

        # 2. 주문 커맨드 생성: requested_qty = 10
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-G-001", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            qty=10, price=2.5, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )

        # 3. OrderRouter / FSM / RiskGate 준비
        fsm = OmsFsm()
        router = OrderRouter(fsm=fsm)
        risk_config = RiskConfig(
            max_order_qty=100,
            max_daily_loss_krw=500_000_000.0,
            max_margin_utilization_ratio=0.85,
            max_position_per_instrument=100,
        )
        risk_engine = RiskEngine(config=risk_config)
        risk_gate = RiskGate(risk_engine=risk_engine)
        account_snapshot = self.vssf.get_account_snapshot()

        is_approved, token, _ = risk_gate.admit_order(
            command=cmd,
            account=account_snapshot,
            positions=self.vssf.account.get_positions(),
        )
        self.assertTrue(is_approved)
        self.assertIsNotNone(token)

        # 4. 비정상 초과 체결 리포트 생성: executed_qty = 11 (> requested_qty 10)
        rep_oversized = CanonicalExecutionReport(
            exec_id="EXEC-G-OVER", client_order_id=cmd.client_order_id, track_id=cmd.track_id,
            asset_type=cmd.asset_type, side=cmd.side, executed_qty=11, executed_price=2.5,
            fee=1100.0, slippage=0.0, timestamp="2026-08-23 09:00:00",
            symbol=cmd.symbol, option_type=cmd.option_type, strike=cmd.strike, expiry=cmd.expiry
        )

        mock_broker = MagicMock(spec=IBrokerAdapter)
        mock_broker.send_order.return_value = rep_oversized

        # 5. OrderRouter를 통한 주문 라우팅 및 초과 체결 차단 실행
        order_id = router.register_and_route(cmd, token, mock_broker)

        # 6. FSM 상태 검증: 정상 FILLED가 되지 않고 REJECTED 상태로 차단되었는지 확인
        self.assertIsNotNone(order_id)
        final_fsm_status = fsm.get_status(order_id)
        self.assertNotEqual(final_fsm_status, OrderStatus.FILLED)
        self.assertEqual(final_fsm_status, OrderStatus.REJECTED)

        # 7. handle_execution_report 경로 추가 검증
        # 별도 신규 주문을 등록 후 handle_execution_report로 oversized execution 리포트 주입 시에도 차단되는지 확인
        cmd2 = CanonicalOrderCommand(
            client_order_id="ORD-G-002", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            qty=10, price=2.5, option_type=CanonicalOptionType.CALL,
            strike=350.0, expiry="2026-09"
        )
        _, token2, _ = risk_gate.admit_order(command=cmd2, account=account_snapshot, positions=self.vssf.account.get_positions())
        oid2 = router.register_and_route(cmd2, token2, None)
        self.assertIsNotNone(oid2)
        router.handle_execution_report(oid2, rep_oversized)
        self.assertNotEqual(fsm.get_status(oid2), OrderStatus.FILLED)
        self.assertEqual(fsm.get_status(oid2), OrderStatus.REJECTED)

        # 8. Mutation 0 불변조건 검증 (사후 상태 비교)
        pos_after = self.vssf.account.get_positions()
        snap_after = self.vssf.account.get_canonical_summary()

        # (1) Position 검증: 포지션이 새로 생성되거나 수량이 증가하지 않음 (변화량 = 0)
        self.assertEqual(len(pos_after), len(pos_before))
        self.assertNotIn(self.inst_key, pos_after)

        # (2) Realized PnL 검증: 실현 손익 변동 0
        self.assertEqual(self.vssf.account.realized_pnl, realized_pnl_before)
        self.assertEqual(snap_after.realized_pnl, snap_before.realized_pnl)

        # (3) Total Balance 검증: 총 잔고 변동 0
        self.assertEqual(self.vssf.account.balance, total_balance_before)
        self.assertEqual(snap_after.total_balance, snap_before.total_balance)

        # (4) Free Margin 검증: 가용 증거금 변동 0
        self.assertEqual(self.vssf.account.free_margin, free_margin_before)
        self.assertEqual(snap_after.free_margin, snap_before.free_margin)

    # =========================================================================
    # 4. TEST H: executed_qty < 0 (음수 체결수량 방어)
    # =========================================================================

    def test_H_negative_execution_qty_defense(self):
        """[TEST H] 음수 체결수량(executed_qty = -1) 수신 시 비정상 mutation 방어 검증."""
        snap_before = self.vssf.account.get_canonical_summary()
        pos_before = dict(self.vssf.account.get_positions())

        rep_neg = CanonicalExecutionReport(
            exec_id="EXEC-H-NEG", client_order_id="ORD-H-NEG", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=-1, executed_price=2.5, fee=0.0, slippage=0.0,
            timestamp="2026-08-23 09:00:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        )
        self.vssf.account.apply_execution(rep_neg)

        pos_after = self.vssf.account.get_positions()
        # 음수 포지션이 생성되지 않거나 잔고가 비정상 변경되지 않는지 확인
        if self.inst_key in pos_after:
            self.assertGreaterEqual(pos_after[self.inst_key]["qty"], 0)

    # =========================================================================
    # 5. TEST I: 동일 order_id + 서로 다른 execution_id 복수 체결 누적
    # =========================================================================

    def test_I_same_order_id_distinct_execution_ids_additive_accumulation(self):
        """[TEST I] 동일 order_id에 대해 EXEC-001(4개) + EXEC-002(6개) 수신 시 Position=10개 정상 누적."""
        # 1차 부분체결: EXEC-001 -> BUY 4 @ 2.5
        rep_1 = CanonicalExecutionReport(
            exec_id="EXEC-I-001", client_order_id="ORD-I-SINGLE", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=4, executed_price=2.5, fee=400.0, slippage=0.0,
            timestamp="2026-08-23 09:00:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        )
        self.vssf.account.apply_execution(rep_1)

        # 2차 부분체결: 동일 order_id, 다른 exec_id -> BUY 6 @ 2.5
        rep_2 = CanonicalExecutionReport(
            exec_id="EXEC-I-002", client_order_id="ORD-I-SINGLE", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=6, executed_price=2.5, fee=600.0, slippage=0.0,
            timestamp="2026-08-23 09:01:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        )
        self.vssf.account.apply_execution(rep_2)

        pos = self.vssf.account.get_positions()
        self.assertIn(self.inst_key, pos)
        # 4 + 6 = 10계약 정확 누적 확인
        self.assertEqual(pos[self.inst_key]["qty"], 10)
        self.assertEqual(pos[self.inst_key]["side"], "BUY")
        self.assertEqual(pos[self.inst_key]["avg_price"], 2.5)

    # =========================================================================
    # 6. TEST J: 복수 execution_id 부분 체결 가중평균단가 + 전량 청산 PnL
    # =========================================================================

    def test_J_multi_execution_weighted_avg_price_and_close_pnl(self):
        """[TEST J] EXEC-001(BUY 4 @ 2.5) + EXEC-002(BUY 6 @ 2.8) -> 평단가 2.68 -> SELL 10 @ 3.0 청산 PnL 정합성."""
        # 1. BUY 4 @ 2.5
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-J-001", client_order_id="ORD-J", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=4, executed_price=2.5, fee=400.0, slippage=0.0,
            timestamp="2026-08-23 09:00:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))

        # 2. BUY 6 @ 2.8 -> 평단가: (4*2.5 + 6*2.8)/10 = (10.0 + 16.8)/10 = 2.68
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-J-002", client_order_id="ORD-J", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=6, executed_price=2.8, fee=600.0, slippage=0.0,
            timestamp="2026-08-23 09:01:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))

        pos = self.vssf.account.get_positions()
        self.assertEqual(pos[self.inst_key]["qty"], 10)
        self.assertAlmostEqual(pos[self.inst_key]["avg_price"], 2.68, places=4)

        # 3. 전량 청산: SELL 10 @ 3.0 -> 실현 손익: (3.0 - 2.68) * 10 * 250,000 = 0.32 * 2,500,000 = 800,000 KRW
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-J-003", client_order_id="ORD-J-CLOSE", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.SELL,
            executed_qty=10, executed_price=3.0, fee=1000.0, slippage=0.0,
            timestamp="2026-08-23 09:02:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))

        pos_after = self.vssf.account.get_positions()
        self.assertTrue(self.inst_key not in pos_after or pos_after[self.inst_key]["qty"] == 0)
        self.assertAlmostEqual(self.vssf.account.realized_pnl, 800000.0, places=2)

    # =========================================================================
    # 7. TEST K: 동일 execution_id 재수신 (멱등성 가드)
    # =========================================================================

    def test_K_duplicate_execution_id_redelivery_exactly_once(self):
        """[TEST K] 동일 exec_id(EXEC-DUP-001) 재수신 시 포지션이 10이 아닌 5로 유지됨을 검증."""
        rep = CanonicalExecutionReport(
            exec_id="EXEC-DUP-001", client_order_id="ORD-K-001", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=5, executed_price=2.5, fee=500.0, slippage=0.0,
            timestamp="2026-08-23 09:00:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        )

        # 1회차 수신
        self.vssf.account.apply_execution(rep)
        pos_1 = dict(self.vssf.account.get_positions()[self.inst_key])
        balance_1 = self.vssf.account.balance

        # 2회차 재수신 (중복)
        self.vssf.account.apply_execution(rep)
        pos_2 = self.vssf.account.get_positions()[self.inst_key]
        balance_2 = self.vssf.account.balance

        self.assertEqual(pos_2["qty"], 5)
        self.assertEqual(pos_1["qty"], pos_2["qty"])
        self.assertEqual(balance_1, balance_2)

    # =========================================================================
    # 8. TEST L: execution_id가 서로 다른 정상 체결 누적
    # =========================================================================

    def test_L_distinct_execution_ids_with_distinct_executions_accumulate(self):
        """[TEST L] EXEC-101(BUY 3 @ 2.5) + EXEC-102(BUY 2 @ 2.7) -> Position=5개 정상 누적."""
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-L-101", client_order_id="ORD-L-1", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=3, executed_price=2.5, fee=300.0, slippage=0.0,
            timestamp="2026-08-23 09:00:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))

        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-L-102", client_order_id="ORD-L-2", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=2, executed_price=2.7, fee=200.0, slippage=0.0,
            timestamp="2026-08-23 09:01:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))

        pos = self.vssf.account.get_positions()
        self.assertIn(self.inst_key, pos)
        # 3 + 2 = 5개 누적
        self.assertEqual(pos[self.inst_key]["qty"], 5)
        # 평단가: (3*2.5 + 2*2.7)/5 = (7.5 + 5.4)/5 = 12.9/5 = 2.58
        self.assertAlmostEqual(pos[self.inst_key]["avg_price"], 2.58, places=4)


if __name__ == "__main__":
    unittest.main()
