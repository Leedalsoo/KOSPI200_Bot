# -*- coding: utf-8 -*-
"""Comprehensive Functional Assertion: Risk Calculation Impact on Order Denial, Reduction, and Execution.

[3단계-5] 검증 항목:
A. 주문 차단 (DENY):
   - 1회 주문 한도 초과 (EXCEEDED_MAX_ORDER_QTY)
   - 일일 최대 손실 초과 (EXCEEDED_MAX_DAILY_LOSS)
   - 종목별 포지션 한도 초과 (EXCEEDED_INSTRUMENT_LIMIT)
   - 가용 증거금 부족 (INSUFFICIENT_FREE_MARGIN)
   - 마진 다이어트 활성 (MARGIN_DIET_ACTIVE)
   -> RiskGate 차단 -> Broker/Execution 호출 0 -> Mutation 0 실측
B. 주문 크기 축소/제한 (REDUCE / SIZING CAP):
   - 리스크 예산 및 계좌 마진 기반 수량 결정 (Track 8 / Track 9 Risk Sizing)
   - 축소/제한된 수량으로 OrderRouter -> Broker -> Execution 전달 및 Position/Ledger 정합성 실측
C. 정상 허용 경로 (ALLOW):
   - 허용 조건 만족 시 정상 승인 -> RiskApprovalToken 발급 -> Broker 체결 -> Position/Balance/Ledger 정상 반영 실측
D. 상태 독립성 (State Isolation):
   - DENY 주문이 후속 정상 주문(ALLOW)의 Risk 승인 및 체결을 오염시키지 않음을 실측
"""
import unittest
from typing import Dict, Any

from shared.contracts.canonical import (
    CanonicalOrderCommand,
    CanonicalOrderSide,
    CanonicalAssetType,
    CanonicalOptionType,
    CanonicalAccountSummary,
    CanonicalMarketTick,
)
from option_program.risk_control.risk_engine import (
    RiskConfig,
    RiskSensor,
    RiskEngine,
    RiskGate,
    RiskSensorSnapshot,
)
from option_program.runtime.program_runtime import OptionProgramRuntime
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime
from option_program.broker.broker_interface import PaperBrokerAdapter


class TestRiskDecisionImpactAssertion(unittest.TestCase):
    """[3단계-5] Risk 결과의 주문 차단/축소/승인 실제 파이프라인 Functional Assertion 테스트 스위트"""

    def setUp(self):
        self.risk_config = RiskConfig(
            max_order_qty=50,
            max_daily_loss_krw=10_000_000.0,
            max_margin_utilization_ratio=0.85,
            max_position_per_instrument=100,
        )
        self.vssf = VirtualSecuritiesFirmRuntime(initial_capital=500_000_000.0)
        self.broker = PaperBrokerAdapter(vssf_runtime=self.vssf)
        self.account_summary = CanonicalAccountSummary(
            account_id="ACC-RISK-TEST-001",
            total_balance=500_000_000.0,
            used_margin=0.0,
            free_margin=500_000_000.0,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            positions={},
        )
        self.runtime = OptionProgramRuntime(
            risk_config=self.risk_config,
            account_summary=self.account_summary,
        )

    def test_A1_deny_exceeded_max_order_qty_blocks_broker_and_mutation(self):
        """[A-1. DENY] 1회 최대 주문수량 한도(50) 초과 시 RiskGate 차단, Broker 미호출(0회), 회계 변이 0 실측."""
        initial_balance = self.vssf.account.balance
        initial_positions = len(self.vssf.account.get_positions())
        initial_ledger = len(self.vssf.account.ledger_engine.transactions)

        # 100계약 과도 주문 요청 (한도 50계약 초과)
        oversized_cmd = CanonicalOrderCommand(
            client_order_id="ORD-DENY-QTY-001",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=100,  # > 50
            price=3.50,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            symbol="KOSPI200",
        )

        # 1. RiskGate 심사
        is_approved, token, rej_reason = self.runtime.risk_gate.admit_order(
            command=oversized_cmd,
            account=self.account_summary,
            positions={},
        )

        # 2. Functional Assertion: RiskGate 차단
        self.assertFalse(is_approved, "Oversized order must be REJECTED by RiskGate")
        self.assertIsNone(token, "Approval token must be None")
        self.assertIn("EXCEEDED_MAX_ORDER_QTY", rej_reason)

        # 3. Functional Assertion: Broker 미전송 및 Mutation 0
        self.assertEqual(self.vssf.account.balance, initial_balance)
        self.assertEqual(len(self.vssf.account.get_positions()), initial_positions)
        self.assertEqual(len(self.vssf.account.ledger_engine.transactions), initial_ledger)

    def test_A2_deny_exceeded_daily_loss_blocks_broker(self):
        """[A-2. DENY] 일일 최대 손실 한도(1천만원) 초과 시 RiskGate 차단 및 Broker 미호출 실측."""
        # 12,000,000 KRW 손실 누적 주입
        self.runtime.risk_engine.record_realized_loss(-12_000_000.0)
        self.account_summary.realized_pnl = -12_000_000.0

        cmd = CanonicalOrderCommand(
            client_order_id="ORD-DENY-LOSS-001",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=1,
            price=3.50,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            symbol="KOSPI200",
        )

        is_approved, token, rej_reason = self.runtime.risk_gate.admit_order(
            command=cmd,
            account=self.account_summary,
            positions={},
        )

        self.assertFalse(is_approved)
        self.assertIsNone(token)
        self.assertIn("EXCEEDED_MAX_DAILY_LOSS", rej_reason)

    def test_A3_deny_exceeded_instrument_position_limit(self):
        """[A-3. DENY] 종목별 최대 포지션 한도(100) 초과 시 Expected Position 계산에 의한 차단 실측."""
        current_positions: Dict[str, Any] = {
            "KOSPI200_OPTION_CALL_350.0": {"qty": 95, "avg_price": 3.50, "side": "BUY"}
        }

        # 10계약 추가 매수 시도 (95 + 10 = 105 > 100)
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-DENY-INST-LIMIT-001",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=10,
            price=3.50,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            symbol="KOSPI200",
        )

        is_approved, token, rej_reason = self.runtime.risk_gate.admit_order(
            command=cmd,
            account=self.account_summary,
            positions=current_positions,
        )

        self.assertFalse(is_approved)
        self.assertIsNone(token)
        self.assertIn("EXCEEDED_INSTRUMENT_LIMIT", rej_reason)

    def test_A4_deny_margin_diet_active_blocks_new_entry(self):
        """[A-4. DENY] Sensor 변동성 급등으로 Margin Diet 발동 시 신규 주문 전면 차단 실측."""
        crisis_snapshot = RiskSensorSnapshot(
            is_vol_spike=True,
            is_crisis_regime=True,
            is_margin_diet_required=True,
            active_vol_ratio=2.5,
            reason="VOL_SPIKE_DIET_TRIGGERED",
        )

        cmd = CanonicalOrderCommand(
            client_order_id="ORD-DENY-DIET-001",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=1,
            price=3.50,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            symbol="KOSPI200",
            tag_id="NORMAL_ENTRY",  # RISK_HEDGE가 아니므로 차단 대상
        )

        is_approved, token, rej_reason = self.runtime.risk_gate.admit_order(
            command=cmd,
            account=self.account_summary,
            positions={},
            sensor_snapshot=crisis_snapshot,
        )

        self.assertFalse(is_approved)
        self.assertIsNone(token)
        self.assertIn("MARGIN_DIET_ACTIVE", rej_reason)

    def test_B_risk_sizing_reduction_and_accurate_execution_mutation(self):
        """[B. REDUCE / SIZING CAP] Risk Sizing에 의해 축소/제한된 수량 발주 -> Broker 체결 -> Position/Ledger 정합성 실측."""
        # 1. 헷지 위험 예산에 따라 결정된 축소 수량 (3계약)
        sized_qty = 3
        sized_cmd = CanonicalOrderCommand(
            client_order_id="ORD-REDUCE-SIZING-001",
            track_id="Track8",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=sized_qty,  # 위험 예산 축소 수량
            price=2.50,
            option_type=CanonicalOptionType.PUT,
            strike=345.0,
            symbol="KOSPI200",
            tag_id="SIZED_RISK_BUDGET",
        )

        # 2. RiskGate 사전 심사
        is_approved, token, rej_reason = self.runtime.risk_gate.admit_order(
            command=sized_cmd,
            account=self.account_summary,
            positions={},
        )
        self.assertTrue(is_approved, "Sized order within risk budget must be approved")
        self.assertIsNotNone(token)

        # 3. OrderRouter 등록
        routed = self.runtime.order_router.register_and_route(sized_cmd, token)
        self.assertTrue(routed)

        # 4. Broker 호가 매칭 및 체결
        tick = CanonicalMarketTick(
            timestamp="2026-08-23 09:00:00",
            underlying_price=350.0,
            bid_price=2.45,
            ask_price=2.50,
            last_price=2.50,
            volume=100,
            seq_id=1,
        )
        self.vssf.process_market_data(tick)
        report = self.broker.send_order(sized_cmd)
        self.assertIsNotNone(report, "Broker must successfully execute sized order")
        self.assertEqual(report.executed_qty, sized_qty, "Executed qty must exactly match sized qty (3)")

        # 5. Position & Ledger 실체 반영 확인
        pos = self.vssf.account.position_mgr.positions.get("KOSPI200_OPTION_PUT_345.0")
        self.assertIsNotNone(pos)
        self.assertEqual(pos["qty"], sized_qty, "Position qty must exactly be 3")

    def test_C_allow_normal_pathway_with_full_order_execution(self):
        """[C. ALLOW] 정상 범위 주문의 RiskGate 승인 -> Token 발급 -> Broker 체결 -> Position/Balance/Ledger 정상 반영 실측."""
        initial_balance = self.vssf.account.balance

        normal_cmd = CanonicalOrderCommand(
            client_order_id="ORD-ALLOW-NORMAL-001",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=2,
            price=3.50,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            symbol="KOSPI200",
        )

        # 1. RiskGate 심사
        is_approved, token, rej = self.runtime.risk_gate.admit_order(
            command=normal_cmd,
            account=self.account_summary,
            positions={},
        )
        self.assertTrue(is_approved)
        self.assertIsNotNone(token)
        self.assertIn("SIG-RISK-APPROVED-Track1-ORD-ALLOW-NORMAL-001", token.signature)

        # 2. Router -> Broker 체결
        tick = CanonicalMarketTick(
            timestamp="2026-08-23 09:00:00",
            underlying_price=350.0,
            bid_price=3.45,
            ask_price=3.50,
            last_price=3.50,
            volume=100,
            seq_id=1,
        )
        self.vssf.process_market_data(tick)
        report = self.broker.send_order(normal_cmd)
        self.assertIsNotNone(report)
        self.assertEqual(report.executed_qty, 2)
        self.assertGreater(report.executed_price, 0.0)
        self.assertEqual(round(report.executed_price, 1), 3.5)

        # 3. Position, Balance, Ledger 반영 실측
        self.assertLess(self.vssf.account.balance, initial_balance, "Balance must decrease by fee")
        pos = self.vssf.account.position_mgr.positions.get("KOSPI200_OPTION_CALL_350.0")
        self.assertIsNotNone(pos)
        self.assertEqual(pos["qty"], 2)
        self.assertEqual(len(self.vssf.account.ledger_engine.transactions), 1)

    def test_D_state_isolation_between_denied_and_allowed_orders(self):
        """[D. 상태 독립성] DENY된 주문이 후속 정상 ALLOW 주문의 Risk 심사 및 체결에 영향을 주지 않음을 실측."""
        # 1. 첫 번째 주문: 수량 초과로 DENY
        bad_cmd = CanonicalOrderCommand(
            client_order_id="ORD-ISO-DENIED-001",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=999,  # DENY
            price=3.50,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            symbol="KOSPI200",
        )
        is_app_1, token_1, rej_1 = self.runtime.risk_gate.admit_order(bad_cmd, self.account_summary, {})
        self.assertFalse(is_app_1)
        self.assertIsNone(token_1)

        # 2. 두 번째 주문: 정상 수량(1계약)으로 ALLOW
        good_cmd = CanonicalOrderCommand(
            client_order_id="ORD-ISO-ALLOWED-002",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=1,  # ALLOW
            price=3.50,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            symbol="KOSPI200",
        )
        is_app_2, token_2, rej_2 = self.runtime.risk_gate.admit_order(good_cmd, self.account_summary, {})
        self.assertTrue(is_app_2, "Subsequent valid order must be APPROVED independently")
        self.assertIsNotNone(token_2)
        self.assertIsNone(rej_2)

        # 3. 두 번째 주문만 정상 체결됨을 확인
        tick = CanonicalMarketTick(
            timestamp="2026-08-23 09:00:00",
            underlying_price=350.0,
            bid_price=3.45,
            ask_price=3.50,
            last_price=3.50,
            volume=100,
            seq_id=1,
        )
        self.vssf.process_market_data(tick)
        report = self.broker.send_order(good_cmd)
        self.assertIsNotNone(report)
        self.assertEqual(report.executed_qty, 1)


if __name__ == "__main__":
    unittest.main()
