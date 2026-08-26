"""E2E Test: 실제 Runtime -> 실제 VSSF Broker -> Execution -> Position/PnL Risk 승인/차단 실체 검증.

검증 핵심 경로:
    [OptionProgramRuntime / Strategy]
        ↓
    [RiskSensor.scan_risk]
        ↓
    [RiskEngine.evaluate_order]
        ↓
    [RiskGate.admit_order]
        ↓ (승인 시 RiskApprovalToken 발급 / 거부 시 token=None)
    [OrderRouter.register_and_route]
        ↓
    [실제 VSSF PaperBrokerAdapter.send_order]
        ↓
    [VSSF ExecutionEngine (Slippage & Fee) -> CanonicalExecutionReport]
        ↓
    [VSSF PositionManager (Actual Position Mutation & Avg Price)]
        ↓
    [VSSF PnLEngine / PaperTradingAccount (PnL, Balance, Margin Mutation)]

필수 검증 시나리오:
- TEST A (Risk 승인 -> 실제 VSSF 주문 체결 -> Position/PnL/Margin 실제 변동):
  1) 실제 VirtualSecuritiesFirmRuntime 및 실제 PaperBrokerAdapter 구성
  2) 실제 OptionProgramRuntime 및 RiskGate에서 정상 주문 심사
  3) RiskGate APPROVE 및 유효한 RiskApprovalToken 발급 실측
  4) OrderRouter가 실제 PaperBrokerAdapter.send_order() 호출
  5) VSSF 호가창 매칭 및 ExecutionEngine을 통해 실제 CanonicalExecutionReport 발급 실측
  6) VSSF PositionManager에 실제 Position 생성 (0 -> 10계약, 평단가 및 수량 일치) 실측
  7) 계좌 사용 마진 및 가용 잔고 실제 변동 실측
  8) OrderRouter 및 OMS FSM이 FILLED 상태로 정상 완료됨을 실측

- TEST B (Risk 차단 -> VSSF 미호출 -> Execution 없음 -> Position/PnL/Balance Mutation = 0):
  1) B1: 일일 손실 한도(1천만원) 초과 계좌 상태 -> RiskGate DENY (EXCEEDED_MAX_DAILY_LOSS)
  2) B2: 마진 다이어트 긴급 위험 상태 -> RiskGate DENY (MARGIN_DIET_ACTIVE)
  3) B3: 1회 최대 수량 한도(50계약) 초과 -> RiskGate DENY (EXCEEDED_MAX_ORDER_QTY)
  4) 각 차단 케이스에서:
     - RiskApprovalToken 미발급 (None)
     - OrderRouter에서 VSSF Broker 호출 차단
     - VSSF 체결 리포트 생성 건수 = 0건
     - Position mutation = 0 (수량/평단가 변동 없음)
     - PnL mutation = 0 (실현손익 변동 없음)
     - Balance mutation = 0 (예수금 변동 없음)
     - Margin mutation = 0 (증거금 변동 없음)
"""
import unittest

from shared.contracts.canonical import (
    CanonicalMarketTick,
    CanonicalOrderCommand,
    CanonicalOrderSide,
    CanonicalAssetType,
    CanonicalOptionType,
    CanonicalAccountSummary,
)
from shared.core.contracts import OrderStatus, RiskApprovalToken
from option_program.risk_control.risk_engine import (
    RiskConfig,
    RiskSensor,
    RiskEngine,
    RiskGate,
)
from option_program.orders.order_router import OrderRouter
from option_program.orders.oms_fsm import OmsFsm
from option_program.broker.broker_interface import BrokerFactory, BrokerMode
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime


class TestRuntimeVssfRiskExecutionPositionPnlE2E(unittest.TestCase):
    """실제 Runtime -> 실제 VSSF Broker -> Execution -> Position/PnL Risk 승인/차단 E2E 검증."""

    def setUp(self):
        self.initial_capital = 50_000_000.0  # 5,000만원
        # 1. 실제 VSSF 가상 증권사 런타임 생성
        self.vssf = VirtualSecuritiesFirmRuntime(initial_capital=self.initial_capital)
        # 2. 실제 VSSF와 연결된 PaperBrokerAdapter 생성
        self.broker = BrokerFactory.create_broker(mode=BrokerMode.PAPER, vssf_runtime=self.vssf)
        
        self.risk_config = RiskConfig(
            max_order_qty=50,
            max_daily_loss_krw=10_000_000.0,
            max_margin_utilization_ratio=0.85,
            max_position_per_instrument=100,
            vol_spike_threshold_multiplier=1.30,
        )
        self.risk_sensor = RiskSensor(config=self.risk_config)
        self.risk_engine = RiskEngine(config=self.risk_config, risk_sensor=self.risk_sensor)
        self.risk_gate = RiskGate(risk_engine=self.risk_engine)
        self.fsm = OmsFsm()
        self.order_router = OrderRouter(fsm=self.fsm)

        self.inst_key = "KOSPI200_OPTION_2026-09_CALL_350.0"

        # 기초 시장 시세 주입 (2.5pt)
        self.base_tick = CanonicalMarketTick(
            timestamp="2026-08-23 09:00:00.000",
            underlying_price=2.5,
            bid_price=2.49,
            ask_price=2.50,
            last_price=2.5,
            volume=1000,
            seq_id=1,
        )
        self.vssf.process_market_data(self.base_tick)
        self.account_summary = self.vssf.get_account_snapshot()

    # =========================================================================
    # TEST A: Risk 승인 -> 실제 VSSF Broker 실행 -> Execution -> Position/PnL 변동
    # =========================================================================

    def test_A_approved_order_executes_real_vssf_and_mutates_position_and_account(self):
        """[TEST A] Risk 승인 -> 실제 VSSF Broker 호출 -> 실제 ExecutionReport -> Actual Position 및 Account 실제 변동."""
        # 1. 사전 상태 스냅샷 (Before)
        pos_before = dict(self.vssf.account.get_positions())
        pnl_before = self.vssf.account.realized_pnl
        bal_before = self.vssf.account.balance
        used_margin_before = self.vssf.account.used_margin
        exec_count_before = len(self.vssf.execution_engine.reports)

        self.assertEqual(len(pos_before), 0)
        self.assertEqual(pnl_before, 0.0)
        self.assertEqual(bal_before, self.initial_capital)
        self.assertEqual(used_margin_before, 0.0)
        self.assertEqual(exec_count_before, 0)

        # 2. Risk Sensor 관측 (정상 상태)
        sensor_snapshot = self.risk_sensor.scan_risk(
            active_vol=1.0,
            base_vol=1.0,
            current_regime="NORMAL",
            account_margin_ratio=(self.account_summary.used_margin / self.account_summary.total_balance)
        )
        self.assertFalse(sensor_snapshot.is_margin_diet_required)

        # 3. 주문 명령 생성 (10계약 @ 2.5)
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-REAL-VSSF-001",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=10,
            price=2.5,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
        )

        # 4. RiskGate 심사 실행
        is_approved, token, reason = self.risk_gate.admit_order(
            command=cmd,
            account=self.account_summary,
            positions=pos_before,
            sensor_snapshot=sensor_snapshot
        )

        # [검증 1] RiskGate 승인 결과 == True 및 RiskApprovalToken 발급 확인
        self.assertTrue(is_approved)
        self.assertIsNone(reason)
        self.assertIsNotNone(token)
        self.assertIsInstance(token, RiskApprovalToken)

        # 5. OrderRouter를 통해 실제 VSSF PaperBrokerAdapter로 라우팅
        order_id = self.order_router.register_and_route(
            command=cmd,
            token=token,
            broker_adapter=self.broker,
            mode_str="PAPER"
        )

        # [검증 2] OrderRouter 등록 및 FSM 상태가 FILLED로 전이되었는지 확인
        self.assertIsNotNone(order_id)
        self.assertEqual(order_id, token.order_id)
        self.assertEqual(self.fsm.get_status(order_id), OrderStatus.FILLED)

        # [검증 3] 실제 VSSF ExecutionEngine에서 ExecutionReport 생성 확인
        exec_count_after = len(self.vssf.execution_engine.reports)
        self.assertEqual(exec_count_after, exec_count_before + 1)
        latest_report = self.vssf.execution_engine.reports[-1]
        self.assertEqual(latest_report.client_order_id, cmd.client_order_id)
        self.assertEqual(latest_report.executed_qty, 10)
        self.assertGreater(latest_report.executed_price, 0.0)

        # [검증 4] 실제 VSSF PositionManager에 Actual Position 생성 및 변동 확인 (Mutation 발생)
        pos_after = dict(self.vssf.account.get_positions())
        self.assertIn(self.inst_key, pos_after)
        self.assertEqual(pos_after[self.inst_key]["qty"], 10)
        self.assertEqual(pos_after[self.inst_key]["side"], "BUY")
        self.assertEqual(pos_after[self.inst_key]["avg_price"], latest_report.executed_price)
        self.assertNotEqual(len(pos_after), len(pos_before))

        # [검증 5] 실제 VSSF 계좌 증거금 변동 확인
        used_margin_after = self.vssf.account.used_margin
        self.assertGreater(used_margin_after, used_margin_before)

        # 6. 추가 검증: 시장 가격 하락(1.5pt) 후 실제 손실 매도 청산 실행 -> Realized PnL 실제 변동 실측
        drop_tick = CanonicalMarketTick(
            timestamp="2026-08-23 09:05:00.000",
            underlying_price=1.5,
            bid_price=1.50,
            ask_price=1.51,
            last_price=1.5,
            volume=500,
            seq_id=2,
        )
        self.vssf.process_market_data(drop_tick)
        account_snap_2 = self.vssf.get_account_snapshot()

        exit_cmd = CanonicalOrderCommand(
            client_order_id="ORD-REAL-VSSF-EXIT-001",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.SELL,
            qty=10,
            price=1.5,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
        )
        is_app_exit, token_exit, _ = self.risk_gate.admit_order(
            command=exit_cmd,
            account=account_snap_2,
            positions=pos_after,
            sensor_snapshot=sensor_snapshot
        )
        self.assertTrue(is_app_exit)
        self.assertIsNotNone(token_exit)

        order_id_exit = self.order_router.register_and_route(
            command=exit_cmd,
            token=token_exit,
            broker_adapter=self.broker,
            mode_str="PAPER"
        )
        self.assertIsNotNone(order_id_exit)
        self.assertEqual(self.fsm.get_status(order_id_exit), OrderStatus.FILLED)

        # 포지션 완전 청산 (FLAT) 및 실제 Realized PnL 손실 발생 실측
        pos_final = dict(self.vssf.account.get_positions())
        self.assertEqual(pos_final.get(self.inst_key, {}).get("qty", 0), 0)
        pnl_final = self.vssf.account.realized_pnl
        self.assertLess(pnl_final, 0.0)  # 실제 손실 발생 확인
        self.assertNotEqual(pnl_final, pnl_before)

    # =========================================================================
    # TEST B: Risk 차단 -> VSSF 미호출 -> Execution 없음 -> Position/PnL Mutation 0
    # =========================================================================

    def test_B1_risk_denial_by_daily_loss_blocks_vssf_execution_with_zero_mutation(self):
        """[TEST B1] 일일 손실 한도 초과 차단 -> VSSF 미호출 -> Execution 없음 -> Position/PnL/Balance Mutation = 0."""
        # 1. 사전 상태 스냅샷
        pos_before = dict(self.vssf.account.get_positions())
        pnl_before = self.vssf.account.realized_pnl
        bal_before = self.vssf.account.balance
        used_margin_before = self.vssf.account.used_margin
        exec_count_before = len(self.vssf.execution_engine.reports)

        # 손실 초과 계좌 스냅샷 (실현 손실 -15,000,000 KRW >= 한도 10,000,000 KRW)
        loss_summary = CanonicalAccountSummary(
            account_id="ACC-TEST-LOSS",
            total_balance=35_000_000.0,
            realized_pnl=-15_000_000.0,
            unrealized_pnl=0.0,
            used_margin=0.0,
            free_margin=35_000_000.0,
        )

        sensor_snapshot = self.risk_sensor.scan_risk(
            active_vol=1.0, base_vol=1.0, current_regime="NORMAL", account_margin_ratio=0.0
        )

        cmd = CanonicalOrderCommand(
            client_order_id="ORD-BLOCKED-VSSF-DAILY-LOSS",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=5,
            price=2.5,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
        )

        # 2. RiskGate 심사 실행 -> DENY
        is_approved, token, reason = self.risk_gate.admit_order(
            command=cmd,
            account=loss_summary,
            positions=pos_before,
            sensor_snapshot=sensor_snapshot
        )

        # [검증 1] RiskGate 차단 판정 및 Token 미발급 확인
        self.assertFalse(is_approved)
        self.assertIn("EXCEEDED_MAX_DAILY_LOSS", reason)
        self.assertIsNone(token)

        # 3. OrderRouter에 차단 주문 라우팅 시도
        order_id = self.order_router.register_and_route(
            command=cmd,
            token=token,
            broker_adapter=self.broker,
            mode_str="PAPER"
        )

        # [검증 2] OrderRouter에서 거부 (order_id is None)
        self.assertIsNone(order_id)

        # [검증 3] 실제 VSSF ExecutionEngine에 새 체결 리포트가 생성되지 않음 확인 (0건)
        exec_count_after = len(self.vssf.execution_engine.reports)
        self.assertEqual(exec_count_after, exec_count_before)

        # [검증 4] 불변조건: Position mutation = 0, PnL mutation = 0, Balance mutation = 0, Margin mutation = 0
        pos_after = dict(self.vssf.account.get_positions())
        pnl_after = self.vssf.account.realized_pnl
        bal_after = self.vssf.account.balance
        used_margin_after = self.vssf.account.used_margin

        self.assertEqual(pos_after, pos_before)
        self.assertEqual(pnl_after, pnl_before)
        self.assertEqual(bal_after, bal_before)
        self.assertEqual(used_margin_after, used_margin_before)

    def test_B2_risk_denial_by_sensor_margin_diet_blocks_vssf_execution_with_zero_mutation(self):
        """[TEST B2] RiskSensor 마진 다이어트 긴급 차단 -> VSSF 미호출 -> Execution 없음 -> Mutation = 0."""
        pos_before = dict(self.vssf.account.get_positions())
        pnl_before = self.vssf.account.realized_pnl
        bal_before = self.vssf.account.balance
        exec_count_before = len(self.vssf.execution_engine.reports)

        # 마진 다이어트 스냅샷 (마진 사용률 92% > 85%)
        sensor_diet = self.risk_sensor.scan_risk(
            active_vol=1.0, base_vol=1.0, current_regime="NORMAL", account_margin_ratio=0.92
        )
        self.assertTrue(sensor_diet.is_margin_diet_required)

        cmd = CanonicalOrderCommand(
            client_order_id="ORD-BLOCKED-VSSF-SENSOR-DIET",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=10,
            price=2.5,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
            tag_id="NORMAL_ENTRY"
        )

        is_approved, token, reason = self.risk_gate.admit_order(
            command=cmd,
            account=self.account_summary,
            positions=pos_before,
            sensor_snapshot=sensor_diet
        )

        self.assertFalse(is_approved)
        self.assertIn("MARGIN_DIET_ACTIVE", reason)
        self.assertIsNone(token)

        order_id = self.order_router.register_and_route(cmd, token, self.broker, "PAPER")
        self.assertIsNone(order_id)

        # 체결 없음 및 불변조건 검증
        self.assertEqual(len(self.vssf.execution_engine.reports), exec_count_before)
        self.assertEqual(dict(self.vssf.account.get_positions()), pos_before)
        self.assertEqual(self.vssf.account.realized_pnl, pnl_before)
        self.assertEqual(self.vssf.account.balance, bal_before)

    def test_B3_risk_denial_by_max_order_qty_blocks_vssf_execution_with_zero_mutation(self):
        """[TEST B3] 1회 최대 수량 한도(50계약) 초과(100계약) 차단 -> VSSF 미호출 -> Execution 없음 -> Mutation = 0."""
        pos_before = dict(self.vssf.account.get_positions())
        pnl_before = self.vssf.account.realized_pnl
        bal_before = self.vssf.account.balance
        exec_count_before = len(self.vssf.execution_engine.reports)

        sensor_snapshot = self.risk_sensor.scan_risk(
            active_vol=1.0, base_vol=1.0, current_regime="NORMAL", account_margin_ratio=0.0
        )

        cmd = CanonicalOrderCommand(
            client_order_id="ORD-BLOCKED-VSSF-MAX-QTY",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=100,  # 50계약 한도 초과
            price=2.5,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
        )

        is_approved, token, reason = self.risk_gate.admit_order(
            command=cmd,
            account=self.account_summary,
            positions=pos_before,
            sensor_snapshot=sensor_snapshot
        )

        self.assertFalse(is_approved)
        self.assertIn("EXCEEDED_MAX_ORDER_QTY", reason)
        self.assertIsNone(token)

        order_id = self.order_router.register_and_route(cmd, token, self.broker, "PAPER")
        self.assertIsNone(order_id)

        # 체결 없음 및 불변조건 검증
        self.assertEqual(len(self.vssf.execution_engine.reports), exec_count_before)
        self.assertEqual(dict(self.vssf.account.get_positions()), pos_before)
        self.assertEqual(self.vssf.account.realized_pnl, pnl_before)
        self.assertEqual(self.vssf.account.balance, bal_before)


if __name__ == "__main__":
    unittest.main()
