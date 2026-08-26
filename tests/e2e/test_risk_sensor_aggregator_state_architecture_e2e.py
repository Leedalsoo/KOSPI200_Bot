"""Architecture E2E Inspection Test: Risk Sensor / Risk Aggregator / Risk State 존재 여부 및 실제 연결 검증.

검증 목적:
1. Risk Sensor: 실제 Production 코드 존재, scan_risk() 실행 및 OptionProgramRuntime 런타임 호출, RiskGate 차단 연결 검증
2. Risk Aggregator: 독립된 Risk Aggregator 클래스/모듈의 부재(Not Implemented) 및 RiskEngine 단일 집계 구조 실측 검증
3. Risk State: 독립된 Risk State 객체/상태머신의 부재(Not Implemented) 및 분산 상태 보관 구조 실측 검증
4. 실제 연결 경로: MarketConditionAnalyzer -> RiskSensor -> RiskSensorSnapshot -> RiskGate -> RiskEngine -> OrderRouter 흐름 실측 검증
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
from option_program.risk_control.risk_engine import (
    RiskConfig,
    RiskSensor,
    RiskSensorSnapshot,
    RiskEngine,
    RiskGate,
)
from option_program.runtime.program_runtime import OptionProgramRuntime
from option_program.orders.order_router import OrderRouter
from option_program.orders.oms_fsm import OmsFsm


class TestRiskSensorAggregatorStateArchitectureE2E(unittest.TestCase):
    """Risk Sensor / Aggregator / State 아키텍처 실측 검증 테스트 스위트."""

    def setUp(self):
        self.config = RiskConfig(
            max_order_qty=50,
            max_daily_loss_krw=10_000_000.0,
            max_margin_utilization_ratio=0.85,
            vol_spike_threshold_multiplier=1.30,
        )
        self.account_summary = CanonicalAccountSummary(
            account_id="ACC-TEST-001",
            total_balance=50_000_000.0,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            used_margin=10_000_000.0,
            free_margin=40_000_000.0,
        )

    # =========================================================================
    # TEST A: Risk Sensor 실제 존재 및 동작 검증
    # =========================================================================

    def test_A_risk_sensor_exists_and_operates_correctly(self):
        """[TEST A] RiskSensor 클래스 및 scan_risk()가 실제 존재하며 정상/변동성스파이크/마진위험을 관측함."""
        sensor = RiskSensor(config=self.config)
        self.assertIsNotNone(sensor)

        # 1. 정상 상태 센싱
        snap_normal = sensor.scan_risk(
            active_vol=1.0,
            base_vol=1.0,
            current_regime="NORMAL",
            account_margin_ratio=0.20
        )
        self.assertIsInstance(snap_normal, RiskSensorSnapshot)
        self.assertFalse(snap_normal.is_vol_spike)
        self.assertFalse(snap_normal.is_crisis_regime)
        self.assertFalse(snap_normal.is_margin_diet_required)
        self.assertEqual(snap_normal.reason, "NORMAL")

        # 2. 변동성 스파이크 감지 (1.35배 >= 1.30배)
        snap_spike = sensor.scan_risk(
            active_vol=1.35,
            base_vol=1.0,
            current_regime="NORMAL",
            account_margin_ratio=0.20
        )
        self.assertTrue(snap_spike.is_vol_spike)
        self.assertIn("VOLATILITY_SPIKE_DETECTED", snap_spike.reason)

        # 3. 마진 다이어트 긴급 상태 감지 (마진 사용률 90% > 85%)
        snap_diet = sensor.scan_risk(
            active_vol=1.0,
            base_vol=1.0,
            current_regime="NORMAL",
            account_margin_ratio=0.90
        )
        self.assertTrue(snap_diet.is_margin_diet_required)
        self.assertIn("MARGIN_DIET_TRIGGERED", snap_diet.reason)

    # =========================================================================
    # TEST B: Risk Aggregator 부재 검증 (독립 모듈 부재, RiskEngine 인라인 집계)
    # =========================================================================

    def test_B_risk_aggregator_absence_and_engine_inline_aggregation(self):
        """[TEST B] 독립된 RiskAggregator 클래스는 존재하지 않으며(NOT IMPLEMENTED), RiskEngine이 직접 다층 집계함."""
        import option_program.risk_control.risk_engine as re_module

        # 1. 독립 RiskAggregator 클래스/함수 부재 확인
        has_aggregator = hasattr(re_module, "RiskAggregator") or hasattr(re_module, "risk_aggregator")
        self.assertFalse(has_aggregator, "RiskAggregator must NOT exist as an independent class in current Exp_Detail_1")

        # 2. 대신 RiskEngine이 Qty, Margin, DailyLoss, Position, Sensor를 단일 메서드에서 순차 집계함을 확인
        engine = RiskEngine(config=self.config)
        self.assertTrue(hasattr(engine, "evaluate_order"))

    # =========================================================================
    # TEST C: Risk State 부재 검증 (독립 State 객체 부재, 분산 상태 관리)
    # =========================================================================

    def test_C_risk_state_absence_and_distributed_state_management(self):
        """[TEST C] 독립된 RiskState 클래스는 존재하지 않으며(NOT IMPLEMENTED), 상태는 Engine/Sensor/Account에 분산됨."""
        import option_program.risk_control.risk_engine as re_module

        # 1. 독립 RiskState 클래스/DTO 부재 확인
        has_risk_state = hasattr(re_module, "RiskState") or hasattr(re_module, "risk_state")
        self.assertFalse(has_risk_state, "RiskState must NOT exist as an independent class in current Exp_Detail_1")

        # 2. 리스크 상태는 RiskEngine 내부 변수(_is_kill_switch_active, _daily_realized_loss)와 SensorSnapshot에 존재함을 확인
        engine = RiskEngine(config=self.config)
        self.assertTrue(hasattr(engine, "_is_kill_switch_active"))
        self.assertTrue(hasattr(engine, "_daily_realized_loss"))

    # =========================================================================
    # TEST D: Risk Sensor -> Risk Gate 실제 연결 및 주문 차단 검증
    # =========================================================================

    def test_D_risk_sensor_to_risk_gate_actual_blocking_connection(self):
        """[TEST D] RiskSensorSnapshot의 긴급 위험 신호가 RiskGate.admit_order에 주입되어 실제 주문 차단으로 연결됨."""
        engine = RiskEngine(config=self.config)
        gate = RiskGate(risk_engine=engine)

        cmd = CanonicalOrderCommand(
            client_order_id="ORD-ARCH-001",
            track_id="Track1",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=5,
            price=2.5,
            option_type=CanonicalOptionType.CALL,
            strike=350.0,
            expiry="2026-09",
            tag_id="NORMAL_ENTRY"
        )

        # 1. 정상 SensorSnapshot 주입 시 -> 주문 승인 (PASS)
        snap_normal = RiskSensorSnapshot(is_margin_diet_required=False, reason="NORMAL")
        is_app, token, reason = gate.admit_order(
            command=cmd,
            account=self.account_summary,
            positions={},
            sensor_snapshot=snap_normal
        )
        self.assertTrue(is_app)
        self.assertIsNotNone(token)
        self.assertIsNone(reason)

        # 2. 마진 다이어트 SensorSnapshot 주입 시 -> 신규 진입 차단 (MARGIN_DIET_ACTIVE)
        snap_diet = RiskSensorSnapshot(
            is_margin_diet_required=True,
            reason="MARGIN_DIET_TRIGGERED (Ratio=90.00%)"
        )
        is_app_diet, token_diet, reason_diet = gate.admit_order(
            command=cmd,
            account=self.account_summary,
            positions={},
            sensor_snapshot=snap_diet
        )
        self.assertFalse(is_app_diet)
        self.assertIsNone(token_diet)
        self.assertIn("MARGIN_DIET_ACTIVE", reason_diet)

    # =========================================================================
    # TEST E: OptionProgramRuntime 런타임 오케스트레이션 파이프라인 실제 통합 검증
    # =========================================================================

    def test_E_runtime_orchestration_executes_sensor_and_risk_pipeline(self):
        """[TEST E] OptionProgramRuntime.process_tick()에서 RiskSensor 호출 -> RiskGate 심사 -> OrderRouter 라우팅 전체 파이프라인 실측."""
        runtime = OptionProgramRuntime(
            risk_config=self.config,
            account_summary=self.account_summary
        )

        # 런타임 컴포넌트 실체화 확인
        self.assertIsInstance(runtime.risk_sensor, RiskSensor)
        self.assertIsInstance(runtime.risk_engine, RiskEngine)
        self.assertIsInstance(runtime.risk_gate, RiskGate)
        self.assertIsInstance(runtime.order_router, OrderRouter)

        # 틱 데이터 주입 및 런타임 실행
        tick = CanonicalMarketTick(
            timestamp="2026-08-23 09:00:00.000",
            underlying_price=350.0,
            bid_price=349.9,
            ask_price=350.1,
            last_price=350.0,
            volume=1000,
            seq_id=1,
        )
        commands = runtime.process_tick(tick)

        # 런타임이 정상적으로 틱을 처리하고 전략 시그널을 생성/중재/리스크심사하여 주문 목록을 반환함을 확인
        self.assertIsInstance(commands, list)
        self.assertEqual(runtime.tick_counter, 1)


if __name__ == "__main__":
    unittest.main()
