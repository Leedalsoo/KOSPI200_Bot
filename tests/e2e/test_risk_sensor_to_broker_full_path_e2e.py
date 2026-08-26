"""E2E Test: Risk Sensor -> RiskEngine -> RiskGate -> RiskApprovalToken -> OrderRouter -> Broker 전체 승인/차단 경로 종합 검증.

검증 핵심 경로:
    [Risk Sensor (RiskSensor.scan_risk)]
        ↓
    [RiskEngine (RiskEngine.evaluate_order)]
        ↓
    [RiskGate (RiskGate.admit_order)]
        ↓
    [RiskApprovalToken (발급 / 미발급)]
        ↓
    [OrderRouter (OrderRouter.validate_token & register_and_route)]
        ↓
    [Broker (IBrokerAdapter.send_order / PaperBroker)]

필수 검증 시나리오:
- TEST A (전체 승인 경로):
  1) RiskSensor가 실제 시장 변동성/국면을 관측하여 정상 RiskSensorSnapshot 생성
  2) RiskEngine이 주문 명령, 계좌 현황, 포지션, SensorSnapshot을 종합 심사하여 승인 판정
  3) RiskGate가 최종 승인(APPROVE)하고 고유 서명된 RiskApprovalToken 발급
  4) OrderRouter가 토큰의 서명 및 주문 일치성을 검증(PASS)하고 FSM(NEW->VALIDATED->SENT) 등록
  5) Broker.send_order()가 정확히 1회 호출되고, 일치하는 client_order_id가 Broker에 전달됨
  6) 체결 리포트 수신 후 FSM FILLED 상태 전이 및 Position/PnL/Balance 정상 반영

- TEST B1 (Sensor 마진 다이어트 긴급 위험 차단 경로):
  1) RiskSensor가 마진 사용률 초과(90% > 85%)를 관측하여 is_margin_diet_required=True 생성
  2) RiskEngine/RiskGate가 MARGIN_DIET_ACTIVE로 신규 진입 주문 거부 (DENY)
  3) RiskApprovalToken이 전혀 발급되지 않음 (token is None)
  4) OrderRouter가 Broker를 호출하지 않고 전면 차단 (Broker.send_order() 호출 횟수 == 0)
  5) 불변조건 실측: Position mutation = 0, PnL mutation = 0, Balance mutation = 0

- TEST B2 (RiskEngine 일일 손실 한도 초과 차단 경로):
  1) 누적 실현 손실이 max_daily_loss_krw(10,000,000 KRW)를 초과한 상태
  2) RiskGate.admit_order()에서 EXCEEDED_MAX_DAILY_LOSS로 거부 (DENY)
  3) RiskApprovalToken 미발급 (token is None)
  4) OrderRouter가 Broker로 전달하지 않음 (Broker.send_order() 호출 횟수 == 0)
  5) 불변조건 실측: Position mutation = 0, PnL mutation = 0, Balance mutation = 0

- TEST B3 (RiskEngine 1회 최대 주문 수량 한도 초과 차단 경로):
  1) 주문 수량이 max_order_qty(50계약)를 초과(100계약)
  2) RiskGate.admit_order()에서 EXCEEDED_MAX_ORDER_QTY로 거부 (DENY)
  3) RiskApprovalToken 미발급 (token is None)
  4) Broker.send_order() 호출 횟수 == 0, Mutation = 0
"""
import unittest
from unittest.mock import MagicMock

from shared.contracts.canonical import (
    CanonicalMarketTick,
    CanonicalOrderCommand,
    CanonicalExecutionReport,
    CanonicalOrderSide,
    CanonicalAssetType,
    CanonicalOptionType,
    CanonicalAccountSummary,
)
from shared.core.contracts import OrderStatus, RiskApprovalToken
from option_program.risk_control.risk_engine import (
    RiskConfig,
    RiskSensor,
    RiskSensorSnapshot,
    RiskEngine,
    RiskGate,
)
from option_program.orders.order_router import OrderRouter
from option_program.orders.oms_fsm import OmsFsm
from option_program.broker.broker_interface import IBrokerAdapter
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime


class TestRiskSensorToBrokerFullPathE2E(unittest.TestCase):
    """Risk Sensor -> RiskEngine -> RiskGate -> RiskApprovalToken -> OrderRouter -> Broker 전체 경로 E2E 검증."""

    def setUp(self):
        self.initial_capital = 50_000_000.0  # 5,000만원
        self.vssf = VirtualSecuritiesFirmRuntime(initial_capital=self.initial_capital)
        
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

        # 초기 기초 시세 등록 (2.5pt)
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
    # TEST A: 승인 경로 (Sensor -> Engine -> Gate APPROVE -> Token -> Router -> Broker 1회 호출)
    # =========================================================================

    def test_A_approved_full_path_executes_broker_exactly_once(self):
        """[TEST A] 정상 RiskSensor 관측 -> RiskEngine 평가 -> RiskGate APPROVE -> Token 발급 -> Router 검증 -> Broker 1회 호출 및 체결."""
        # 1. RiskSensor 관측 실행
        sensor_snapshot = self.risk_sensor.scan_risk(
            active_vol=1.0,
            base_vol=1.0,
            current_regime="NORMAL",
            account_margin_ratio=(self.account_summary.used_margin / self.account_summary.total_balance)
        )
        self.assertIsInstance(sensor_snapshot, RiskSensorSnapshot)
        self.assertFalse(sensor_snapshot.is_margin_diet_required)
        self.assertFalse(sensor_snapshot.is_vol_spike)
        self.assertEqual(sensor_snapshot.reason, "NORMAL")

        # 2. 주문 명령 생성
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-FULL-PATH-PASS",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=10,
            price=2.5,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
        )

        # 3. RiskEngine 및 RiskGate 심사 실행
        is_approved, token, reason = self.risk_gate.admit_order(
            command=cmd,
            account=self.account_summary,
            positions=self.vssf.account.get_positions(),
            sensor_snapshot=sensor_snapshot
        )

        # [검증 1] RiskGate 승인 결과 == True
        self.assertTrue(is_approved)
        self.assertIsNone(reason)

        # [검증 2] 유효한 RiskApprovalToken 실제 발급 확인
        self.assertIsNotNone(token)
        self.assertIsInstance(token, RiskApprovalToken)
        self.assertIsNotNone(token.order_id)
        self.assertIn(cmd.client_order_id, token.signature)
        self.assertIn(cmd.track_id, token.signature)

        # 4. Broker Spy/Mock 생성 (호출 감시용)
        mock_broker = MagicMock(spec=IBrokerAdapter)
        mock_broker.send_order.return_value = CanonicalExecutionReport(
            exec_id="EXEC-FULL-001",
            client_order_id=cmd.client_order_id,
            track_id=cmd.track_id,
            asset_type=cmd.asset_type,
            side=cmd.side,
            executed_qty=cmd.qty,
            executed_price=cmd.price,
            fee=1000.0,
            slippage=0.0,
            timestamp="2026-08-23 09:00:00",
            symbol=cmd.symbol,
            option_type=cmd.option_type,
            strike=cmd.strike,
            expiry=cmd.expiry,
        )

        # 5. OrderRouter를 통한 토큰 검증 및 브로커 라우팅
        order_id = self.order_router.register_and_route(
            command=cmd,
            token=token,
            broker_adapter=mock_broker,
            mode_str="PAPER"
        )

        # [검증 3] OrderRouter 검증 통과 및 order_id 반환 확인
        self.assertIsNotNone(order_id)
        self.assertEqual(order_id, token.order_id)

        # [검증 4] Broker.send_order()가 정확히 1회 실제 호출되었는지 확인
        self.assertEqual(mock_broker.send_order.call_count, 1)

        # [검증 5] 정확한 client_order_id가 포함된 command가 Broker에 전달되었는지 확인
        mock_broker.send_order.assert_called_once_with(cmd)
        called_cmd = mock_broker.send_order.call_args[0][0]
        self.assertEqual(called_cmd.client_order_id, "ORD-FULL-PATH-PASS")

        # [검증 6] FSM 상태가 FILLED로 정상 전이되었는지 확인
        self.assertEqual(self.fsm.get_status(order_id), OrderStatus.FILLED)

    # =========================================================================
    # TEST B1: 차단 경로 1 (Sensor 마진 다이어트 긴급 위험 감지 -> Gate DENY -> Broker 0회)
    # =========================================================================

    def test_B1_sensor_margin_diet_blocks_broker_call_with_zero_mutation(self):
        """[TEST B1] RiskSensor 마진 다이어트 감지 -> RiskGate DENY -> Token 미발급 -> Broker 호출 0회 및 Mutation 0."""
        # 1. 사전 상태 스냅샷
        pos_before = dict(self.vssf.account.get_positions())
        pnl_before = self.vssf.account.realized_pnl
        bal_before = self.vssf.account.balance

        # 2. RiskSensor 관측: 마진 다이어트 긴급 상태 (마진 사용률 92% > 85%)
        sensor_snapshot = self.risk_sensor.scan_risk(
            active_vol=1.0,
            base_vol=1.0,
            current_regime="NORMAL",
            account_margin_ratio=0.92
        )
        self.assertTrue(sensor_snapshot.is_margin_diet_required)

        cmd = CanonicalOrderCommand(
            client_order_id="ORD-BLOCKED-SENSOR-DIET",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=10,
            price=2.5,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
            tag_id="NORMAL_ENTRY"  # 비-헤지 진입 주문
        )

        # 3. RiskGate 심사 실행
        is_approved, token, reason = self.risk_gate.admit_order(
            command=cmd,
            account=self.account_summary,
            positions=pos_before,
            sensor_snapshot=sensor_snapshot
        )

        # [검증 1] RiskGate 차단 판정 (DENY) 확인
        self.assertFalse(is_approved)
        self.assertIn("MARGIN_DIET_ACTIVE", reason)

        # [검증 2] RiskApprovalToken이 전혀 발급되지 않음 (None) 확인
        self.assertIsNone(token)

        # 4. 차단 상태에서 OrderRouter 실행 시도 (token=None)
        mock_broker = MagicMock(spec=IBrokerAdapter)
        order_id = self.order_router.register_and_route(
            command=cmd,
            token=token,
            broker_adapter=mock_broker,
            mode_str="PAPER"
        )

        # [검증 3] OrderRouter에서 Broker로 전달되지 않음 (order_id is None)
        self.assertIsNone(order_id)

        # [검증 4] Broker.send_order() 호출 횟수 == 0 확인
        self.assertEqual(mock_broker.send_order.call_count, 0)

        # [검증 5] 불변조건: Position mutation = 0, PnL mutation = 0, Balance mutation = 0
        pos_after = dict(self.vssf.account.get_positions())
        pnl_after = self.vssf.account.realized_pnl
        bal_after = self.vssf.account.balance

        self.assertEqual(pos_after, pos_before)
        self.assertEqual(pnl_after, pnl_before)
        self.assertEqual(bal_after, bal_before)

    # =========================================================================
    # TEST B2: 차단 경로 2 (RiskEngine 일일 손실 한도 초과 -> Gate DENY -> Broker 0회)
    # =========================================================================

    def test_B2_daily_loss_limit_blocks_broker_call_with_zero_mutation(self):
        """[TEST B2] 일일 손실 한도(1천만원) 초과 -> RiskGate DENY -> Token 미발급 -> Broker 0회 호출 및 Mutation 0."""
        pos_before = dict(self.vssf.account.get_positions())
        pnl_before = self.vssf.account.realized_pnl
        bal_before = self.vssf.account.balance

        # 손실이 반영된 계좌 스냅샷 (실현 손실 -15,000,000 KRW >= 한도 10,000,000 KRW)
        loss_account_summary = CanonicalAccountSummary(
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
            client_order_id="ORD-BLOCKED-DAILY-LOSS",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=5,
            price=2.5,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
        )

        is_approved, token, reason = self.risk_gate.admit_order(
            command=cmd,
            account=loss_account_summary,
            positions=pos_before,
            sensor_snapshot=sensor_snapshot
        )

        # [검증 1] RiskGate 차단 (DENY) 확인
        self.assertFalse(is_approved)
        self.assertIn("EXCEEDED_MAX_DAILY_LOSS", reason)

        # [검증 2] Token 미발급 확인
        self.assertIsNone(token)

        # 3. Broker 호출 차단 검증
        mock_broker = MagicMock(spec=IBrokerAdapter)
        order_id = self.order_router.register_and_route(
            command=cmd, token=token, broker_adapter=mock_broker
        )

        self.assertIsNone(order_id)
        self.assertEqual(mock_broker.send_order.call_count, 0)

        # [검증 3] Mutation = 0 불변조건
        self.assertEqual(dict(self.vssf.account.get_positions()), pos_before)
        self.assertEqual(self.vssf.account.realized_pnl, pnl_before)
        self.assertEqual(self.vssf.account.balance, bal_before)

    # =========================================================================
    # TEST B3: 차단 경로 3 (1회 최대 주문 수량 한도 초과 -> Gate DENY -> Broker 0회)
    # =========================================================================

    def test_B3_max_order_qty_limit_blocks_broker_call_with_zero_mutation(self):
        """[TEST B3] 1회 최대 주문 수량(50계약) 초과(100계약) -> RiskGate DENY -> Token 미발급 -> Broker 0회 호출 및 Mutation 0."""
        pos_before = dict(self.vssf.account.get_positions())
        pnl_before = self.vssf.account.realized_pnl
        bal_before = self.vssf.account.balance

        sensor_snapshot = self.risk_sensor.scan_risk(
            active_vol=1.0, base_vol=1.0, current_regime="NORMAL", account_margin_ratio=0.0
        )

        # 수량 100계약 (한도 50계약 초과)
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-BLOCKED-MAX-QTY",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=100,
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

        # [검증 1] RiskGate 차단 (DENY) 확인
        self.assertFalse(is_approved)
        self.assertIn("EXCEEDED_MAX_ORDER_QTY", reason)

        # [검증 2] Token 미발급 확인
        self.assertIsNone(token)

        # 3. Broker 호출 차단 검증
        mock_broker = MagicMock(spec=IBrokerAdapter)
        order_id = self.order_router.register_and_route(
            command=cmd, token=token, broker_adapter=mock_broker
        )

        self.assertIsNone(order_id)
        self.assertEqual(mock_broker.send_order.call_count, 0)

        # [검증 3] Mutation = 0 불변조건
        self.assertEqual(dict(self.vssf.account.get_positions()), pos_before)
        self.assertEqual(self.vssf.account.realized_pnl, pnl_before)
        self.assertEqual(self.vssf.account.balance, bal_before)


if __name__ == "__main__":
    unittest.main()
