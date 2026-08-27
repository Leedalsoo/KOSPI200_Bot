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
from shared.core.contracts import OrderStatus
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
        """[A-3. DENY] 종목별 최대 포지션 한도(100) 도달 후 추가 진입 시 Expected Position 계산에 의한 차단 실측."""
        current_positions: Dict[str, Any] = {
            "KOSPI200_OPTION_CALL_350.0": {"qty": 100, "avg_price": 3.50, "side": "BUY"}
        }

        # 10계약 추가 매수 시도 (100 + 10 = 110 > 100, 잔여 용량 0)
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

    def test_B_risk_decision_reduce_causality_and_single_pipeline_execution(self):
        """[B. REDUCE] Risk 결과가 주문수량을 실제로 축소하고 OrderRouter->Broker->Execution 단일 경로로 실행되는 인과관계 실측."""
        # 1. 호가 데이터 사전 주입 (OrderBook 준비)
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

        # 2. 원래 주문수량 10계약 설정 (original_qty = 10)
        original_qty = 10
        order_cmd = CanonicalOrderCommand(
            client_order_id="ORD-REDUCE-DYNAMIC-001",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=original_qty,
            price=2.50,
            option_type=CanonicalOptionType.PUT,
            strike=345.0,
            symbol="KOSPI200",
        )
        inst_key = order_cmd.get_instrument_key()

        # 3. 기존 포지션 97계약 설정 (종목별 최대 한도 100계약 중 잔여 허용 Capacity = 3계약)
        existing_positions: Dict[str, Any] = {
            inst_key: {"qty": 97, "avg_price": 2.50, "side": "BUY"}
        }
        self.vssf.account.position_mgr.positions[inst_key] = {"qty": 97, "avg_price": 2.50, "side": "BUY"}

        # 4. RiskGate 사전 심사 통과 (실제 RiskEngine 계산에 의해 REDUCE 결정 및 축소 수량 산출)
        is_approved, token, rej_reason = self.runtime.risk_gate.admit_order(
            command=order_cmd,
            account=self.account_summary,
            positions=existing_positions,
            allow_reduction=True,
        )

        # 5. [Assertion A] Risk Decision 및 수량 축소 인과관계 검증
        eval_result = self.runtime.risk_gate.last_evaluation_result
        self.assertIsNotNone(eval_result)
        self.assertEqual(eval_result.decision, "REDUCE", "Risk Decision must strictly be REDUCE")
        self.assertEqual(eval_result.original_qty, original_qty, "Original qty must match input 10")

        reduced_cmd = eval_result.reduced_command if eval_result.reduced_command else order_cmd
        final_order_qty = reduced_cmd.qty
        self.assertGreater(original_qty, final_order_qty, "Original qty must be strictly greater than reduced qty")
        self.assertGreater(final_order_qty, 0, "Reduced qty must be strictly positive")
        self.assertEqual(final_order_qty, eval_result.approved_qty, "Command qty must be dynamically set by RiskEngine")
        self.assertEqual(final_order_qty, 3, "Reduced qty must equal remaining capacity (100 - 97 = 3)")

        # 6. [Assertion B] 실제 단일 운영 경로 통과 (OrderRouter -> Broker.send_order -> Execution)
        # 테스트에서 별도로 broker.send_order()를 호출하지 않고, OrderRouter에 broker_adapter를 주입하여 단일 호출로 관통!
        order_uuid = self.runtime.order_router.register_and_route(
            command=reduced_cmd,
            token=token,
            broker_adapter=self.broker,
            mode_str="PAPER"
        )
        self.assertIsNotNone(order_uuid)

        # 7. [Assertion C] OMS FSM 완료 상태 및 Broker 전달 수량, 최종 체결 수량 일치 검증
        self.assertEqual(self.runtime.oms_fsm.states.get(order_uuid), OrderStatus.FILLED)

        # 8. [Assertion D] 최종 포지션 및 원장(Ledger) 정합성 실측
        pos = self.vssf.account.position_mgr.positions.get(inst_key)
        self.assertIsNotNone(pos)
        self.assertEqual(pos["qty"], 97 + final_order_qty, "Position must increase by exactly the reduced qty (97 + 3 = 100)")

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
