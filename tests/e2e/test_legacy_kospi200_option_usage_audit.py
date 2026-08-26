"""Legacy KOSPI200_OPTION 사용처 전수 조사 및 제거 가능 여부 검증 테스트.

검증 목적:
1. 표준 Instrument Identity 경로(Order -> Execution -> Position -> Risk)에서
   Legacy "KOSPI200_OPTION" 단일 키가 생성되지 않고 표준 정규화 키가 일관되게 사용되는지 검증.
2. RiskEngine이 표준 Instrument Key로 실제 포지션을 100% 매칭하여
   Legacy fallback("KOSPI200_OPTION")에 의존하지 않고 정상 동작하는지 검증.
"""
import sys
import unittest
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
    build_instrument_key,
)
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime  # noqa: E402
from option_program.risk_control.risk_engine import RiskConfig, RiskEngine, RiskGate  # noqa: E402
from option_program.broker.broker_interface import BrokerFactory, BrokerMode  # noqa: E402
from option_program.runtime.program_runtime import OptionProgramRuntime  # noqa: E402


class TestLegacyKospi200OptionUsageAudit(unittest.TestCase):
    """Legacy KOSPI200_OPTION 사용처 및 표준 Identity 일관성 감사 테스트."""

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
        self.op_runtime = OptionProgramRuntime(
            risk_config=self.risk_config,
            account_summary=self.vssf.get_account_snapshot(),
        )

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
        self.op_runtime.update_account_summary(self.vssf.get_account_snapshot())

    def test_01_standard_order_execution_does_not_create_legacy_key(self):
        """[검증 1] 표준 주문 체결 시 Legacy 'KOSPI200_OPTION' 단일 키가 생성되지 않고 정규화 키로만 생성됨."""
        cmd = CanonicalOrderCommand(
            client_order_id="ORD-AUDIT-001",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=10,
            price=2.5,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
        )

        expected_key = "KOSPI200_OPTION_2026-09_CALL_350.0"
        self.assertEqual(cmd.get_instrument_key(), expected_key)

        # 발주 및 체결
        report = self.broker.send_order(cmd)
        self.assertIsNotNone(report)
        self.assertEqual(report.get_instrument_key(), expected_key)

        positions = self.vssf.account.get_positions()
        # 정규화 키 존재 확인
        self.assertIn(expected_key, positions)
        self.assertEqual(positions[expected_key]["qty"], 10)
        # Legacy 단일 키 'KOSPI200_OPTION'이 생성되지 않았음을 확인
        self.assertNotIn("KOSPI200_OPTION", positions)

    def test_02_multiple_instruments_all_use_distinct_standard_keys(self):
        """[검증 2] 다중 옵션 종목 체결 시 모든 포지션이 각각 고유 표준 정규화 키로 관리됨."""
        orders = [
            CanonicalOrderCommand("ORD-A", "Track1", CanonicalAssetType.OPTION, CanonicalOrderSide.BUY, 5, 2.5, CanonicalOptionType.CALL, 350.0, expiry="2026-09"),
            CanonicalOrderCommand("ORD-B", "Track1", CanonicalAssetType.OPTION, CanonicalOrderSide.BUY, 10, 2.5, CanonicalOptionType.CALL, 360.0, expiry="2026-09"),
            CanonicalOrderCommand("ORD-C", "Track1", CanonicalAssetType.OPTION, CanonicalOrderSide.BUY, 15, 2.5, CanonicalOptionType.PUT, 350.0, expiry="2026-09"),
            CanonicalOrderCommand("ORD-D", "Track1", CanonicalAssetType.OPTION, CanonicalOrderSide.BUY, 20, 2.5, CanonicalOptionType.CALL, 350.0, expiry="2026-12"),
        ]

        for o in orders:
            rep = self.broker.send_order(o)
            self.assertIsNotNone(rep)

        positions = self.vssf.account.get_positions()
        self.assertEqual(len(positions), 4)
        self.assertIn("KOSPI200_OPTION_2026-09_CALL_350.0", positions)
        self.assertIn("KOSPI200_OPTION_2026-09_CALL_360.0", positions)
        self.assertIn("KOSPI200_OPTION_2026-09_PUT_350.0", positions)
        self.assertIn("KOSPI200_OPTION_2026-12_CALL_350.0", positions)
        self.assertNotIn("KOSPI200_OPTION", positions)

    def test_03_risk_engine_matches_standard_key_without_legacy_fallback(self):
        """[검증 3] RiskEngine이 표준 Key를 1순위로 조회하여 정확히 매칭함을 확인."""
        # 1. 포지션 사전 생성
        inst_key = "KOSPI200_OPTION_2026-09_CALL_350.0"
        self.vssf.account.apply_execution(CanonicalExecutionReport(
            exec_id="EXEC-AUDIT-3", client_order_id="ORD-AUDIT-3", track_id="Track1",
            asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY,
            executed_qty=50, executed_price=2.5, fee=500.0, slippage=0.0,
            timestamp="2026-08-23 09:00:00", symbol="KOSPI200",
            option_type=CanonicalOptionType.CALL, strike=350.0, expiry="2026-09"
        ))

        # 2. 추가 50계약 주문 (Expected: 100 <= 100 -> PASS)
        cmd_pass = CanonicalOrderCommand("ORD-P", "Track1", CanonicalAssetType.OPTION, CanonicalOrderSide.BUY, 50, 2.5, CanonicalOptionType.CALL, 350.0, expiry="2026-09")
        exp_pass = self.op_runtime.risk_gate.engine.calculate_expected_position(cmd_pass, self.vssf.account.get_positions())
        self.assertEqual(exp_pass["instrument_key"], inst_key)
        self.assertEqual(exp_pass["qty"], 100)

        # 3. 추가 51계약 주문 (Expected: 101 > 100 -> REJECT)
        cmd_rej = CanonicalOrderCommand("ORD-R", "Track1", CanonicalAssetType.OPTION, CanonicalOrderSide.BUY, 51, 2.5, CanonicalOptionType.CALL, 350.0, expiry="2026-09")
        exp_rej = self.op_runtime.risk_gate.engine.calculate_expected_position(cmd_rej, self.vssf.account.get_positions())
        self.assertEqual(exp_rej["instrument_key"], inst_key)
        self.assertEqual(exp_rej["qty"], 101)


if __name__ == "__main__":
    unittest.main()
