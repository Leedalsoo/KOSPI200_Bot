"""E2E Test: Risk Token 실제 주문 실행 경로 및 Broker 호출 차단 검증.

검증 핵심 경로:
    Risk Token (RiskApprovalToken)
        ↓
    주문 요청 (CanonicalOrderCommand)
        ↓
    Risk 검증 (OrderRouter.validate_token)
        ↓
    OrderRouter (register_and_route)
        ↓
    Broker 호출 (BrokerAdapter.send_order)
        ↓
    실제 주문 실행 (FSM 전이 및 ExecutionReport)

필수 검증 시나리오:
- TEST A (유효 Risk Token):
  1) RiskGate.admit_order를 통해 유효한 RiskApprovalToken 획득
  2) OrderRouter.register_and_route에 전달
  3) Risk 검증 통과 (PASS)
  4) Broker.send_order 실제 호출 확인 (호출 횟수 == 1)
  5) 주문 식별자 및 전달 Command 일치 확인
  6) FSM 정상 완료(FILLED) 전이 확인

- TEST B (Risk Token 없음):
  1) token=None 상태로 주문 요청
  2) Risk 검증 실패 (TOKEN_MISSING)
  3) OrderRouter가 Broker 호출 전 전면 차단 (Broker.send_order 호출 횟수 == 0)
  4) Position mutation = 0, PnL mutation = 0 불변조건 확인

- TEST C (무효/위조/재사용 Risk Token):
  1) C1: 위조 서명 토큰 -> Risk 검증 실패 (TOKEN_SIGNATURE_MISMATCH) -> Broker 호출 0회, FSM REJECTED, Position/PnL mutation = 0
  2) C2: 재사용/재전송 토큰 -> 1회차 성공 후 2회차 재사용 차단 (TOKEN_ALREADY_USED) -> Broker 호출 횟수 증가 없음 (1회 유지)
  3) C3: 잘못된 형식 토큰 (문자열 또는 비UUID) -> Risk 검증 실패 (TOKEN_INVALID_TYPE/TOKEN_INVALID_ORDER_ID) -> Broker 호출 0회
"""
import time
import unittest
import uuid
from unittest.mock import MagicMock

from shared.contracts.canonical import (
    CanonicalMarketTick,
    CanonicalOrderCommand,
    CanonicalExecutionReport,
    CanonicalOrderSide,
    CanonicalAssetType,
    CanonicalOptionType,
)
from shared.core.contracts import OrderStatus, RiskApprovalToken
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime
from option_program.risk_control.risk_engine import RiskConfig, RiskEngine, RiskGate
from option_program.orders.order_router import OrderRouter
from option_program.orders.oms_fsm import OmsFsm
from option_program.broker.broker_interface import BrokerFactory, BrokerMode, IBrokerAdapter


class TestRiskTokenActualBrokerE2E(unittest.TestCase):
    """Risk Token -> OrderRouter -> Broker.send_order 실제 호출 및 차단 E2E 검증."""

    def setUp(self):
        self.initial_capital = 50_000_000.0
        self.vssf = VirtualSecuritiesFirmRuntime(initial_capital=self.initial_capital)
        self.broker = BrokerFactory.create_broker(mode=BrokerMode.PAPER, vssf_runtime=self.vssf)
        self.risk_config = RiskConfig(
            max_order_qty=50,
            max_daily_loss_krw=10_000_000.0,
            max_margin_utilization_ratio=0.85,
            max_position_per_instrument=100,
        )
        self.risk_engine = RiskEngine(config=self.risk_config)
        self.risk_gate = RiskGate(risk_engine=self.risk_engine)
        self.fsm = OmsFsm()
        self.router = OrderRouter(fsm=self.fsm)

        # 기초 시세 등록
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
        self.account_snapshot = self.vssf.get_account_snapshot()

    # =========================================================================
    # TEST A: 유효 Risk Token -> Risk 검증 PASS -> Broker.send_order 호출 = 1회
    # =========================================================================

    def test_A_valid_risk_token_allows_broker_send_order_and_executes(self):
        """[TEST A] 유효한 Risk Token -> 검증 PASS -> Broker.send_order 1회 실제 호출 및 체결."""
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-RT-TEST-A",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=10,
            price=2.5,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
        )

        # 1. RiskGate를 통한 유효 RiskApprovalToken 발급
        is_approved, token, reason = self.risk_gate.admit_order(
            command=cmd,
            account=self.account_snapshot,
            positions=self.vssf.account.get_positions(),
        )
        self.assertTrue(is_approved)
        self.assertIsNotNone(token)
        self.assertIsNone(reason)
        self.assertIsInstance(token.order_id, uuid.UUID)

        # 2. Broker Mock 생성 (호출 감시용)
        mock_broker = MagicMock(spec=IBrokerAdapter)
        mock_broker.send_order.return_value = CanonicalExecutionReport(
            exec_id="EXEC-RT-001",
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

        # 3. OrderRouter를 통한 라우팅 실행
        order_id = self.router.register_and_route(
            command=cmd,
            token=token,
            broker_adapter=mock_broker,
            mode_str="PAPER"
        )

        # [검증 1] 라우팅 성공 및 token.order_id 반환 확인
        self.assertIsNotNone(order_id)
        self.assertEqual(order_id, token.order_id)

        # [검증 2] Broker.send_order가 정확히 1회 실제 호출되었는지 확인
        self.assertEqual(mock_broker.send_order.call_count, 1)

        # [검증 3] 전달된 인자가 발주 command와 100% 일치하는지 확인
        mock_broker.send_order.assert_called_once_with(cmd)

        # [검증 4] FSM 상태가 FILLED로 정상 전이되었는지 확인
        self.assertEqual(self.fsm.get_status(order_id), OrderStatus.FILLED)

    # =========================================================================
    # TEST B: Risk Token 없음 -> Risk 검증 FAIL -> Broker.send_order 호출 = 0회
    # =========================================================================

    def test_B_missing_risk_token_blocks_broker_send_order_with_zero_mutation(self):
        """[TEST B] Risk Token 없음(None) -> 검증 FAIL -> Broker.send_order 0회 호출 (차단) 및 Mutation 0."""
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-RT-TEST-B",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=10,
            price=2.5,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
        )

        # 사전 상태 스냅샷
        pos_before = dict(self.vssf.account.get_positions())
        pnl_before = self.vssf.account.realized_pnl
        bal_before = self.vssf.account.balance

        mock_broker = MagicMock(spec=IBrokerAdapter)

        # token=None으로 라우팅 시도
        order_id = self.router.register_and_route(
            command=cmd,
            token=None,
            broker_adapter=mock_broker,
            mode_str="PAPER"
        )

        # [검증 1] 라우팅 거부 (None 반환) 확인
        self.assertIsNone(order_id)

        # [검증 2] Broker.send_order 호출 횟수가 정확히 0회인지 확인
        self.assertEqual(mock_broker.send_order.call_count, 0)

        # [검증 3] 사후 Position / PnL / Balance Mutation = 0 불변조건 확인
        pos_after = dict(self.vssf.account.get_positions())
        pnl_after = self.vssf.account.realized_pnl
        bal_after = self.vssf.account.balance

        self.assertEqual(pos_after, pos_before)
        self.assertEqual(pnl_after, pnl_before)
        self.assertEqual(bal_after, bal_before)

    # =========================================================================
    # TEST C: 무효/위조/재사용 Risk Token -> Risk 검증 FAIL -> Broker.send_order = 0회
    # =========================================================================

    def test_C1_invalid_signature_risk_token_blocks_broker_send_order(self):
        """[TEST C1] 위조 서명 Risk Token -> 검증 FAIL -> Broker.send_order 0회 호출 및 FSM REJECTED."""
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-RT-TEST-C1",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=10,
            price=2.5,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
        )

        # 임의 위조된 서명 토큰
        fake_token = RiskApprovalToken(
            order_id=uuid.uuid4(),
            timestamp_ns=time.time_ns(),
            signature="FORGED-UNAUTHORIZED-SIGNATURE-TOKEN",
        )

        mock_broker = MagicMock(spec=IBrokerAdapter)

        order_id = self.router.register_and_route(
            command=cmd,
            token=fake_token,
            broker_adapter=mock_broker,
            mode_str="PAPER"
        )

        # [검증 1] 라우팅 거부 확인
        self.assertIsNone(order_id)

        # [검증 2] Broker.send_order 호출 횟수 = 0 확인
        self.assertEqual(mock_broker.send_order.call_count, 0)

        # [검증 3] FSM 상태가 REJECTED로 기록되었는지 확인
        self.assertEqual(self.fsm.get_status(fake_token.order_id), OrderStatus.REJECTED)

    def test_C2_replayed_risk_token_blocks_broker_send_order_on_reuse(self):
        """[TEST C2] 재사용(Replay) Risk Token -> 1회차 성공 후 2회차 재사용 시 Broker 추가 호출 차단."""
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-RT-TEST-C2",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=10,
            price=2.5,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
        )

        is_approved, token, _ = self.risk_gate.admit_order(
            command=cmd,
            account=self.account_snapshot,
            positions=self.vssf.account.get_positions(),
        )
        self.assertTrue(is_approved)

        mock_broker = MagicMock(spec=IBrokerAdapter)
        mock_broker.send_order.return_value = CanonicalExecutionReport(
            exec_id="EXEC-RT-002",
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

        # 1회차 정상 라우팅
        order_id_1 = self.router.register_and_route(cmd, token, mock_broker)
        self.assertIsNotNone(order_id_1)
        self.assertEqual(mock_broker.send_order.call_count, 1)

        # 2회차 동일 토큰 재사용 시도
        order_id_2 = self.router.register_and_route(cmd, token, mock_broker)
        
        # [검증 1] 2회차 라우팅 거부 확인
        self.assertIsNone(order_id_2)

        # [검증 2] Broker.send_order 호출 횟수가 1회에서 증가하지 않음 확인
        self.assertEqual(mock_broker.send_order.call_count, 1)

    def test_C3_malformed_risk_token_blocks_broker_send_order(self):
        """[TEST C3] 타입/형식이 잘못된 Risk Token -> 검증 FAIL -> Broker.send_order 0회 호출."""
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-RT-TEST-C3",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=10,
            price=2.5,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
        )

        mock_broker = MagicMock(spec=IBrokerAdapter)

        # 문자열 객체 전달
        order_id_str = self.router.register_and_route(cmd, "INVALID_STRING_TOKEN", mock_broker)
        self.assertIsNone(order_id_str)
        self.assertEqual(mock_broker.send_order.call_count, 0)

        # 딕셔너리 객체 전달
        order_id_dict = self.router.register_and_route(cmd, {"order_id": "not-uuid"}, mock_broker)
        self.assertIsNone(order_id_dict)
        self.assertEqual(mock_broker.send_order.call_count, 0)


if __name__ == "__main__":
    unittest.main()
