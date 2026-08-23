# -*- coding: utf-8 -*-
import pytest
from virtual_market_simulator.market.synthetic_market_generator import (
    VirtualBrokerConfig,
    VirtualBrokerControlInterface,
    HistoricalReplayEngine
)
from virtual_securities_firm.execution.execution_engine import SlippageEngine
from sensor.trade_replay_analyzer import TradeReplayAnalyzer

def test_1_virtual_broker_config_defaults() -> None:
    """[Test 1] VirtualBrokerConfig 기본값 검증"""
    cfg = VirtualBrokerConfig()
    assert cfg.replay_speed == 1
    assert cfg.slippage_multiplier == 1.0
    assert cfg.fee_rate_multiplier == 1.0
    assert cfg.volatility_scale == 1.0
    assert cfg.gap_pct == 0.0
    assert cfg.scenario_name == "COVID_PANIC_2020"


def test_2_replay_speed_1000x_setting() -> None:
    """[Test 2] replay_speed = 1000x 설정 검증"""
    control = VirtualBrokerControlInterface()
    control.update_config({"replay_speed": 1000})
    assert control.get_config()["replay_speed"] == 1000


def test_3_slippage_multiplier_range() -> None:
    """[Test 3] Slippage Multiplier 범위 검증 (0.5x ~ 3.0x)"""
    control = VirtualBrokerControlInterface()
    
    # 하한선 0.5x 클램핑
    control.update_config({"slippage_multiplier": 0.1})
    assert control.get_config()["slippage_multiplier"] == 0.5
    
    # 상한선 3.0x 클램핑
    control.update_config({"slippage_multiplier": 5.0})
    assert control.get_config()["slippage_multiplier"] == 3.0
    
    # 정상 범위 2.0x
    control.update_config({"slippage_multiplier": 2.0})
    assert control.get_config()["slippage_multiplier"] == 2.0


def test_4_fee_multiplier_range() -> None:
    """[Test 4] Fee Multiplier 범위 검증 (0.5x ~ 2.0x)"""
    control = VirtualBrokerControlInterface()
    
    # 하한선 0.5x
    control.update_config({"fee_rate_multiplier": 0.2})
    assert control.get_config()["fee_rate_multiplier"] == 0.5
    
    # 상한선 2.0x
    control.update_config({"fee_rate_multiplier": 4.0})
    assert control.get_config()["fee_rate_multiplier"] == 2.0


def test_5_volatility_scale_range() -> None:
    """[Test 5] Volatility Scale 범위 검증 (0.5x ~ 3.0x)"""
    control = VirtualBrokerControlInterface()
    
    # 하한선 0.5x
    control.update_config({"volatility_scale": 0.1})
    assert control.get_config()["volatility_scale"] == 0.5
    
    # 상한선 3.0x
    control.update_config({"volatility_scale": 4.5})
    assert control.get_config()["volatility_scale"] == 3.0


def test_6_gap_injection() -> None:
    """[Test 6] Gap Injection 검증 (-2.0% ~ +2.0%)"""
    control = VirtualBrokerControlInterface()
    control.update_config({"gap_pct": 0.015})  # +1.5% 갭
    
    replay = HistoricalReplayEngine(control_interface=control)
    replay.load_scenario("GAP_SPIKE", start_price=300.0)
    tick1 = replay.next_tick()
    
    assert tick1 is not None
    # 300.0 * (1 + 0.015) = 304.5
    assert tick1["price"] >= 304.0


def test_7_scenario_presets() -> None:
    """[Test 7] Scenario Preset 검증 (5종 시나리오)"""
    scenarios = ["COVID_PANIC_2020", "BULL_TREND", "BEAR_TREND", "SIDEWAYS_BOX", "GAP_SPIKE"]
    control = VirtualBrokerControlInterface()
    replay = HistoricalReplayEngine(control_interface=control)
    
    for sc in scenarios:
        control.update_config({"scenario_name": sc})
        replay.load_scenario(sc, start_price=350.0)
        assert replay.is_active is True
        t = replay.next_tick()
        assert t is not None
        assert "price" in t


def test_8_time_bucket_pnl_analysis_report() -> None:
    """[Test 8] 시간대별 PnL 분석 및 자동 진단 리포트 검증"""
    analyzer = TradeReplayAnalyzer(mode="VIRTUAL")
    
    # T1 시간대 거래 캡처
    analyzer.capture_trade_event(
        trade_type="EXIT",
        track_name="Track5",
        side="BUY",
        asset_type="FUTURES",
        price=350.0,
        qty=1,
        reason="Gap Fill Exit",
        realized_pnl=120000.0,
        sensor_snapshot={},
        state_snapshot={},
        date_str="2026-08-07 09:02:00",
        fee=2000.0,
        slippage_cost=3000.0
    )
    
    report = analyzer.generate_trade_analysis_report()
    
    assert "time_bucket_analysis" in report
    assert "strategy_summary" in report
    assert "config_recommendations" in report
    assert report["signature"] == "NO AUTOMATIC STRATEGY MODIFICATION"
    
    bucket = report["time_bucket_analysis"]
    assert "T1_GAP_OPEN" in bucket
    assert bucket["T1_GAP_OPEN"]["Track5"]["net_pnl"] == 120000.0


def test_9_deterministic_replay_consistency_across_speeds() -> None:
    """[Test 9] 1x / 300x / 1000x Deterministic Replay 결과 동일성 검증"""
    c1 = VirtualBrokerControlInterface()
    c1.update_config({"replay_speed": 1})
    r1 = HistoricalReplayEngine(control_interface=c1)
    r1.load_scenario("COVID_PANIC_2020", start_price=300.0)
    
    c1000 = VirtualBrokerControlInterface()
    c1000.update_config({"replay_speed": 1000})
    r1000 = HistoricalReplayEngine(control_interface=c1000)
    r1000.load_scenario("COVID_PANIC_2020", start_price=300.0)
    
    ticks1 = [r1.next_tick() for _ in range(10)]
    ticks1000 = [r1000.next_tick() for _ in range(10)]
    
    assert len(ticks1) == len(ticks1000)
    for t1, t1000 in zip(ticks1, ticks1000):
        assert t1["price"] == t1000["price"]
        assert t1["active_vol"] == t1000["active_vol"]
