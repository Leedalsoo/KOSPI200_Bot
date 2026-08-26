"""E2E Test: OrderRouter -> Broker Real Dispatch & RiskApprovalToken Validation.

Covers:
1. RiskApprovalToken validity, integrity, mismatch, replay, missing token defenses.
2. Direct dispatch to BrokerAdapter.send_order() and FSM lifecycle progression.
3. Broker failure / rejection handling (no position mutation, clean FSM rejection).
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
from option_program.runtime.program_runtime import OptionProgramRuntime  # noqa: E402


class TestOrderRouterBrokerRiskTokenE2E(unittest.TestCase):
    """OrderRouter 및 RiskApprovalToken 보호 주문 라우팅 E2E 검증."""

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

        # 틱 시세 주입
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

    def test_01_approved_token_routes_and_executes_broker(self):
        """[TEST 1] 정상 Risk 승인 Token + 주문 -> OrderRouter -> Broker send_order() 실제 호출 -> 성공."""
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-E2E-001",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=10,
            price=2.5,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
        )

        is_approved, token, reason = self.risk_gate.admit_order(
            command=cmd,
            account=self.account_snapshot,
            positions=self.vssf.account.get_positions(),
        )
        self.assertTrue(is_approved)
        self.assertIsNotNone(token)

        # Mock Broker 감시 객체
        mock_broker = MagicMock(spec=IBrokerAdapter)
        mock_broker.send_order.return_value = CanonicalExecutionReport(
            exec_id="EXEC-001",
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

        order_id = self.router.register_and_route(
            command=cmd,
            token=token,
            broker_adapter=mock_broker,
            mode_str="PAPER"
        )

        self.assertIsNotNone(order_id)
        self.assertEqual(order_id, token.order_id)
        # Broker send_order 1회 실제 호출 확인
        self.assertEqual(mock_broker.send_order.call_count, 1)
        mock_broker.send_order.assert_called_once_with(cmd)
        # FSM 상태가 FILLED로 전이됨을 확인
        self.assertEqual(self.fsm.get_status(order_id), OrderStatus.FILLED)

    def test_02_missing_token_blocks_broker_call(self):
        """[TEST 2] Token 없음 (None) -> Broker send_order() 호출 횟수 = 0, Router 거부."""
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-E2E-002",
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
        order_id = self.router.register_and_route(
            command=cmd,
            token=None,
            broker_adapter=mock_broker,
        )

        self.assertIsNone(order_id)
        self.assertEqual(mock_broker.send_order.call_count, 0)

    def test_03_invalid_order_id_token_blocks_broker_call(self):
        """[TEST 3] 잘못된 order_id Token -> Broker send_order() 호출 횟수 = 0, Router 거부."""
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-E2E-003",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=10,
            price=2.5,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
        )

        # order_id가 빈 문자열/None인 비정상 토큰
        fake_token = RiskApprovalToken(
            order_id=None,
            timestamp_ns=time.time_ns(),
            signature="SIG-RISK-APPROVED-Track1-ORD-E2E-003",
        )

        mock_broker = MagicMock(spec=IBrokerAdapter)
        order_id = self.router.register_and_route(
            command=cmd,
            token=fake_token,
            broker_adapter=mock_broker,
        )

        self.assertIsNone(order_id)
        self.assertEqual(mock_broker.send_order.call_count, 0)

    def test_04_token_order_mismatch_blocks_broker_call(self):
        """[TEST 4] 주문 정보와 Token 정보 불일치 (다른 주문의 Token) -> Broker 호출 차단."""
        cmd_a = CanonicalOrderCommand(
            client_order_id="ORD-E2E-004-A",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=10,
            price=2.5,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
        )
        cmd_b = CanonicalOrderCommand(
            client_order_id="ORD-E2E-004-B",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=10,
            price=2.5,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
        )

        # cmd_a 승인 토큰 발급
        _, token_a, _ = self.risk_gate.admit_order(cmd_a, self.account_snapshot, self.vssf.account.get_positions())

        mock_broker = MagicMock(spec=IBrokerAdapter)
        # cmd_b 발주에 token_a를 사용 시도
        order_id = self.router.register_and_route(
            command=cmd_b,
            token=token_a,
            broker_adapter=mock_broker,
        )

        self.assertIsNone(order_id)
        self.assertEqual(mock_broker.send_order.call_count, 0)
        self.assertEqual(self.fsm.get_status(token_a.order_id), OrderStatus.REJECTED)

    def test_05_replayed_token_blocks_broker_call(self):
        """[TEST 5] 무효/재사용 Token (Replay 공격) -> Broker send_order() 2회차 호출 차단."""
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-E2E-005",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=10,
            price=2.5,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
        )

        _, token, _ = self.risk_gate.admit_order(cmd, self.account_snapshot, self.vssf.account.get_positions())

        mock_broker = MagicMock(spec=IBrokerAdapter)
        mock_broker.send_order.return_value = CanonicalExecutionReport(
            exec_id="EXEC-005", client_order_id=cmd.client_order_id, track_id=cmd.track_id,
            asset_type=cmd.asset_type, side=cmd.side, executed_qty=cmd.qty, executed_price=cmd.price,
            fee=1000.0, slippage=0.0, timestamp="2026-08-23 09:00:00"
        )

        # 1회차 정상 라우팅
        oid_1 = self.router.register_and_route(cmd, token, mock_broker)
        self.assertIsNotNone(oid_1)
        self.assertEqual(mock_broker.send_order.call_count, 1)

        # 2회차 동일 토큰 재사용 라우팅 시도
        oid_2 = self.router.register_and_route(cmd, token, mock_broker)
        self.assertIsNone(oid_2)
        # Broker 호출 횟수가 1회에서 증가하지 않음
        self.assertEqual(mock_broker.send_order.call_count, 1)

    def test_06_direct_router_call_without_risk_approval_blocked(self):
        """[TEST 6] Risk 승인 없이 임의 위조 토큰으로 Router 직접 호출 -> Broker 호출 차단."""
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-E2E-006",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=10,
            price=2.5,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
        )

        # 위조된 가짜 서명 토큰
        fake_token = RiskApprovalToken(
            order_id=uuid.uuid4(),
            timestamp_ns=time.time_ns(),
            signature="FORGED-SIGNATURE-WITHOUT-RISK-APPROVAL",
        )

        mock_broker = MagicMock(spec=IBrokerAdapter)
        order_id = self.router.register_and_route(cmd, fake_token, mock_broker)

        self.assertIsNone(order_id)
        self.assertEqual(mock_broker.send_order.call_count, 0)
        self.assertEqual(self.fsm.get_status(fake_token.order_id), OrderStatus.REJECTED)

    def test_07_broker_send_order_failure_leaves_no_position_change(self):
        """[TEST 7] Broker send_order() 실패 -> REJECTED 기록, Position 변화 없음."""
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-E2E-007",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=10,
            price=2.5,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
        )

        _, token, _ = self.risk_gate.admit_order(cmd, self.account_snapshot, self.vssf.account.get_positions())

        # 실패(거부)를 반환하는 Broker
        failing_broker = MagicMock(spec=IBrokerAdapter)
        failing_broker.send_order.return_value = None

        pos_before = dict(self.vssf.account.get_positions())
        order_id = self.router.register_and_route(cmd, token, failing_broker)

        self.assertIsNotNone(order_id)
        self.assertEqual(failing_broker.send_order.call_count, 1)
        # FSM 상태는 REJECTED
        self.assertEqual(self.fsm.get_status(order_id), OrderStatus.REJECTED)
        # 실제 계좌 포지션 변화 없음
        pos_after = self.vssf.account.get_positions()
        self.assertEqual(pos_before, pos_after)

    def test_08_broker_send_order_success_updates_position_via_paper_broker(self):
        """[TEST 8] 실제 PaperBroker 연동 send_order() 성공 -> 호출 1회 확인 및 포지션 생성."""
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-E2E-008",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=15,
            price=2.5,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
        )

        _, token, _ = self.risk_gate.admit_order(cmd, self.account_snapshot, self.vssf.account.get_positions())

        order_id = self.router.register_and_route(cmd, token, self.broker, mode_str="PAPER")

        self.assertIsNotNone(order_id)
        self.assertEqual(self.fsm.get_status(order_id), OrderStatus.FILLED)

        # 실제 PaperTradingAccount에 포지션 반영 확인
        inst_key = cmd.get_instrument_key()
        positions = self.vssf.account.get_positions()
        self.assertIn(inst_key, positions)
        self.assertEqual(positions[inst_key]["qty"], 15)
        self.assertEqual(positions[inst_key]["side"], "BUY")

    def test_09_duplicate_order_routing_idempotency_guard(self):
        """[TEST 9] 동일 Order ID 중복 라우팅 -> 2회차 차단 및 총 호출 1회 유지."""
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-E2E-009",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=5,
            price=2.5,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
        )

        _, token, _ = self.risk_gate.admit_order(cmd, self.account_snapshot, self.vssf.account.get_positions())

        mock_broker = MagicMock(spec=IBrokerAdapter)
        mock_broker.send_order.return_value = CanonicalExecutionReport(
            exec_id="EXEC-009", client_order_id=cmd.client_order_id, track_id=cmd.track_id,
            asset_type=cmd.asset_type, side=cmd.side, executed_qty=cmd.qty, executed_price=cmd.price,
            fee=500.0, slippage=0.0, timestamp="2026-08-23 09:00:00"
        )

        # 1차 라우팅
        oid_1 = self.router.register_and_route(cmd, token, mock_broker)
        self.assertIsNotNone(oid_1)
        self.assertEqual(mock_broker.send_order.call_count, 1)

        # 2차 중복 라우팅 시도
        oid_2 = self.router.register_and_route(cmd, token, mock_broker)
        self.assertIsNone(oid_2)
        # Broker 추가 호출 없이 1회 유지
        self.assertEqual(mock_broker.send_order.call_count, 1)

    def test_10_tampered_order_parameters_against_token_blocked(self):
        """[TEST 10] Risk Token 발급 후 주문 속성(Track/Order ID) 변조 시 Broker 호출 차단."""
        cmd_original = CanonicalOrderCommand(
            client_order_id="ORD-E2E-010-ORIG",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=10,
            price=2.5,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
        )

        _, token, _ = self.risk_gate.admit_order(cmd_original, self.account_snapshot, self.vssf.account.get_positions())

        # 발주 직전 client_order_id 또는 track_id를 변조한 커맨드
        cmd_tampered = CanonicalOrderCommand(
            client_order_id="ORD-E2E-010-TAMPERED",
            track_id="Track2",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=100,  # 수량 임의 증액
            price=2.5,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
        )

        mock_broker = MagicMock(spec=IBrokerAdapter)
        order_id = self.router.register_and_route(cmd_tampered, token, mock_broker)

        self.assertIsNone(order_id)
        self.assertEqual(mock_broker.send_order.call_count, 0)


if __name__ == "__main__":
    unittest.main()
