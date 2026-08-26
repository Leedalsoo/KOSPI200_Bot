"""E2E Test: RiskGate 직접 판정 관측 및 DENY -> Broker 미호출 직접 검증.

3대 핵심 검증 시나리오:
- TEST A: RiskGate.admit_order()의 APPROVE 판정 자체를 직접 호출하여 (is_approved=True, token!=None, rej_reason=None) 반환값을 직접 관측
- TEST B: DENY + EXCEEDED_MAX_DAILY_LOSS 판정 자체를 직접 호출하여 확인하고, 동일 조건의 Production Orchestrator 실행 경로에서 Broker.send_order() 호출 횟수가 0회(call_count == 0)임을 직접 계측
- TEST C: DENY + EXCEEDED_MAX_ORDER_QTY 판정 자체를 직접 호출하여 확인하고, 동일 조건의 Production Orchestrator 실행 경로에서 Broker.send_order() 호출 횟수가 0회(call_count == 0)임을 직접 계측

절대 준수 사항:
- commands == [] 등의 간접 추론이 아닌 Broker.send_order() 실제 호출 횟수(0회)를 직접 계측
- RiskGate.admit_order()의 실제 반환값(is_approved, token, rej_reason)을 직접 assertion
- 테스트 코드가 Broker에 임의로 주문을 수동 발주하지 않음
"""
import unittest
from unittest.mock import MagicMock
import asyncio

from main import TradingSystem
from option_program.risk_control.risk_engine import RiskGate, RiskEngine
from shared.contracts.canonical import (
    CanonicalOrderCommand,
    CanonicalAccountSummary,
    CanonicalOrderSide,
    CanonicalAssetType,
    CanonicalOptionType,
)


class TestRiskGateDirectDecisionBrokerSuppressionE2E(unittest.TestCase):
    """RiskGate.admit_order() 직접 판정 관측 및 DENY 시 Broker 미호출 직접 계측 E2E 검증."""

    def test_A_direct_approve_decision_observation(self):
        """[TEST A] 정상 Risk 상태에서 RiskGate.admit_order() 직접 호출 -> APPROVE 판정 및 RiskApprovalToken 직접 관측."""
        engine = RiskEngine()
        gate = RiskGate(engine)

        account = CanonicalAccountSummary(
            account_id="ACC-TEST-APPROVE",
            total_balance=500_000_000.0,
            used_margin=0.0,
            free_margin=500_000_000.0,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            positions={}
        )

        cmd = CanonicalOrderCommand(
            client_order_id="ORD-APPROVE-TEST-1",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=1,
            price=2.50,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            symbol="KOSPI200"
        )

        # 1. RiskGate.admit_order() 직접 실행
        is_approved, token, rej_reason = gate.admit_order(
            command=cmd,
            account=account,
            positions=account.positions,
            sensor_snapshot=None
        )

        # 2. [직접 증거 1] admit_order()의 반환 판정이 APPROVE (True)인지 직접 assertion
        self.assertTrue(is_approved, "RiskGate.admit_order() must directly return is_approved=True")

        # 3. [직접 증거 2] 발급된 RiskApprovalToken이 유효하고 실제 객체인지 직접 assertion
        self.assertIsNotNone(token, "RiskApprovalToken must not be None on approval")
        self.assertIsNotNone(token.order_id, "Token order_id must be valid UUID")
        self.assertGreater(token.timestamp_ns, 0, "Token timestamp_ns must be positive")
        self.assertIn("SIG-RISK-APPROVED", token.signature, "Token signature must be valid")

        # 4. [직접 증거 3] 거부 사유가 None인지 직접 assertion
        self.assertIsNone(rej_reason, "Rejection reason must be None on approval")

    def test_B_direct_daily_loss_deny_and_broker_suppression(self):
        """[TEST B] DENY + EXCEEDED_MAX_DAILY_LOSS 직접 판정 확인 및 Broker.send_order() 호출 횟수 0회 직접 계측."""
        async def _run():
            # 1. Production Orchestrator 초기화
            system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 500_000_000.0})
            await system.initialize()
            system.op_runtime.risk_config.max_daily_loss_krw = 10_000_000.0

            # 2. 위험 상태 주입 (일일 손실 -1500만원)
            system.vssf.account.realized_pnl = -15_000_000.0
            account_summary = system.vssf.get_account_snapshot()

            cmd = CanonicalOrderCommand(
                client_order_id="ORD-DAILY-LOSS-TEST-1",
                track_id="Track1",
                asset_type=CanonicalAssetType.OPTION,
                side=CanonicalOrderSide.BUY,
                qty=1,
                price=2.50,
                option_type=CanonicalOptionType.CALL,
                strike=350.0,
                symbol="KOSPI200"
            )

            # 3. [직접 증거 1] RiskGate.admit_order() 직접 호출하여 DENY 판정 및 사유 확인
            is_approved, token, rej_reason = system.op_runtime.risk_gate.admit_order(
                command=cmd,
                account=account_summary,
                positions=account_summary.positions,
                sensor_snapshot=None
            )

            self.assertFalse(is_approved, "RiskGate must directly return is_approved=False")
            self.assertIsNone(token, "RiskApprovalToken must be None on DENY")
            self.assertIsNotNone(rej_reason, "Rejection reason must not be None")
            self.assertIn("EXCEEDED_MAX_DAILY_LOSS", rej_reason, "Rejection reason must contain EXCEEDED_MAX_DAILY_LOSS")

            # 4. [직접 증거 2] Broker.send_order()에 spy 계측 설치하여 실제 Orchestrator 런타임 경로 실행 시 호출 여부 계측
            original_send_order = system.broker.send_order
            spy_send_order = MagicMock(side_effect=original_send_order)
            system.broker.send_order = spy_send_order

            # Production Orchestrator 실행 (1 틱)
            await system.run_loop(max_ticks=1)

            # 5. [직접 증거 3] Broker.send_order() 실제 호출 횟수가 0회임을 직접 계측 assertion
            self.assertEqual(spy_send_order.call_count, 0, "Broker.send_order() must be called 0 times under EXCEEDED_MAX_DAILY_LOSS")

            await system.shutdown()

        asyncio.run(_run())

    def test_C_direct_order_qty_deny_and_broker_suppression(self):
        """[TEST C] DENY + EXCEEDED_MAX_ORDER_QTY 직접 판정 확인 및 Broker.send_order() 호출 횟수 0회 직접 계측."""
        async def _run():
            # 1. Production Orchestrator 초기화
            system = TradingSystem(config={"broker_mode": "PAPER", "initial_capital": 500_000_000.0})
            await system.initialize()
            system.op_runtime.risk_config.max_order_qty = 0  # 1회 최대 수량 0으로 제한

            account_summary = system.vssf.get_account_snapshot()

            cmd = CanonicalOrderCommand(
                client_order_id="ORD-QTY-LIMIT-TEST-1",
                track_id="Track1",
                asset_type=CanonicalAssetType.OPTION,
                side=CanonicalOrderSide.BUY,
                qty=1,
                price=2.50,
                option_type=CanonicalOptionType.CALL,
                strike=350.0,
                symbol="KOSPI200"
            )

            # 2. [직접 증거 1] RiskGate.admit_order() 직접 호출하여 DENY 판정 및 사유 확인
            is_approved, token, rej_reason = system.op_runtime.risk_gate.admit_order(
                command=cmd,
                account=account_summary,
                positions=account_summary.positions,
                sensor_snapshot=None
            )

            self.assertFalse(is_approved, "RiskGate must directly return is_approved=False")
            self.assertIsNone(token, "RiskApprovalToken must be None on DENY")
            self.assertIsNotNone(rej_reason, "Rejection reason must not be None")
            self.assertIn("EXCEEDED_MAX_ORDER_QTY", rej_reason, "Rejection reason must contain EXCEEDED_MAX_ORDER_QTY")

            # 3. [직접 증거 2] Broker.send_order()에 spy 계측 설치하여 실제 Orchestrator 런타임 경로 실행 시 호출 여부 계측
            original_send_order = system.broker.send_order
            spy_send_order = MagicMock(side_effect=original_send_order)
            system.broker.send_order = spy_send_order

            # Production Orchestrator 실행 (1 틱)
            await system.run_loop(max_ticks=1)

            # 4. [직접 증거 3] Broker.send_order() 실제 호출 횟수가 0회임을 직접 계측 assertion
            self.assertEqual(spy_send_order.call_count, 0, "Broker.send_order() must be called 0 times under EXCEEDED_MAX_ORDER_QTY")

            await system.shutdown()

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
