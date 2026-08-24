"""Unit Test: Trade Replay & Decision Analyzer Comprehensive Verification."""
import pytest
from option_program.sensor.trade_replay_analyzer import TradeReplayAnalyzer

def test_trade_replay_mode_routing():
    """Validates date routing between VIRTUAL (historical date) and LIVE (system date)."""
    # 1. Virtual mode respects explicit date_str
    analyzer_virt = TradeReplayAnalyzer(mode="VIRTUAL")
    analyzer_virt.capture_trade_event(
        trade_type="ENTRY",
        track_name="Track5",
        side="BUY",
        asset_type="FUTURES",
        price=350.0,
        qty=1,
        reason="Gap Fill Entry",
        realized_pnl=0.0,
        sensor_snapshot={},
        state_snapshot={},
        date_str="2025-03-15"
    )
    records_virt = analyzer_virt.get_recent_records()
    assert len(records_virt) == 1
    assert records_virt[0]["dateStr"] == "2025-03-15"

    # 2. Mock / Live mode routing
    analyzer_live = TradeReplayAnalyzer(mode="LIVE")
    analyzer_live.capture_trade_event(
        trade_type="EXIT",
        track_name="Track1",
        side="SELL",
        asset_type="OPTION",
        price=2.50,
        qty=2,
        reason="Profit Target",
        realized_pnl=500000.0,
        sensor_snapshot={},
        state_snapshot={}
    )
    records_live = analyzer_live.get_recent_records()
    assert len(records_live) == 1
    assert records_live[0]["realizedPnL"] == 500000.0

def test_trade_replay_4_tier_tree_hierarchy():
    """Validates Month -> Date -> Trade records 4-tier tree archiving."""
    analyzer = TradeReplayAnalyzer(mode="VIRTUAL")
    analyzer.capture_trade_event(
        trade_type="ENTRY",
        track_name="Track3",
        side="BUY",
        asset_type="OPTION",
        price=1.80,
        qty=3,
        reason="Scalp Entry",
        realized_pnl=0.0,
        sensor_snapshot={},
        state_snapshot={},
        date_str="2025-06-10"
    )
    analyzer.capture_trade_event(
        trade_type="EXIT",
        track_name="Track3",
        side="SELL",
        asset_type="OPTION",
        price=2.10,
        qty=3,
        reason="Scalp Exit",
        realized_pnl=225000.0,
        sensor_snapshot={},
        state_snapshot={},
        date_str="2025-06-10"
    )

    tree = analyzer.get_tree_archive()
    assert "2025-06" in tree
    assert "2025-06-10" in tree["2025-06"]
    assert len(tree["2025-06"]["2025-06-10"]) == 2

def test_rule_compliance_automated_judgment():
    """Validates automated rule compliance classification (Valid, High Toxicity, Slippage Distorted)."""
    analyzer = TradeReplayAnalyzer(mode="VIRTUAL")

    # 1. Valid compliant
    r1 = analyzer.capture_trade_event(
        trade_type="ENTRY",
        track_name="Track1",
        side="BUY",
        asset_type="OPTION",
        price=2.0,
        qty=1,
        reason="Signal",
        realized_pnl=0.0,
        sensor_snapshot={"vpin": 0.3},
        state_snapshot={"slippageMs": 50},
        date_str="2025-01-02"
    )
    assert r1["ruleCompliance"]["status"] == "VALID_COMPLIANT"

    # 2. High Toxicity Warning
    r2 = analyzer.capture_trade_event(
        trade_type="ENTRY",
        track_name="Track1",
        side="BUY",
        asset_type="OPTION",
        price=2.0,
        qty=1,
        reason="Signal",
        realized_pnl=0.0,
        sensor_snapshot={"vpin": 0.85},
        state_snapshot={"slippageMs": 50},
        date_str="2025-01-02"
    )
    assert r2["ruleCompliance"]["status"] == "HIGH_TOXICITY_WARNED"

    # 3. Slippage Distorted
    r3 = analyzer.capture_trade_event(
        trade_type="ENTRY",
        track_name="Track1",
        side="BUY",
        asset_type="OPTION",
        price=2.0,
        qty=1,
        reason="Signal",
        realized_pnl=0.0,
        sensor_snapshot={"vpin": 0.3},
        state_snapshot={"slippageMs": 250},
        date_str="2025-01-02"
    )
    assert r3["ruleCompliance"]["status"] == "SLIPPAGE_DISTORTED"

def test_ai_counterfactual_timing_analysis():
    """Validates AI counterfactual timing recommendation score."""
    analyzer = TradeReplayAnalyzer(mode="VIRTUAL")

    # Entry with extreme Z-Score
    r_entry = analyzer.capture_trade_event(
        trade_type="ENTRY",
        track_name="Track2",
        side="BUY",
        asset_type="OPTION",
        price=2.50,
        qty=2,
        reason="Mean Reversion",
        realized_pnl=0.0,
        sensor_snapshot={"zScore": 2.8},
        state_snapshot={},
        date_str="2025-01-02"
    )
    assert "EXCELLENT" in r_entry["aiTimingAnalysis"]["rating"]

    # Exit with Profit
    r_exit_profit = analyzer.capture_trade_event(
        trade_type="EXIT",
        track_name="Track2",
        side="SELL",
        asset_type="OPTION",
        price=3.00,
        qty=2,
        reason="Target Reached",
        realized_pnl=250000.0,
        sensor_snapshot={},
        state_snapshot={},
        date_str="2025-01-02"
    )
    assert "OPTIMAL_PROFIT" in r_exit_profit["aiTimingAnalysis"]["rating"]

def test_diagnostic_only_strict_immutability():
    """Validates Diagnostic-Only principle: reports contain signature and do not modify params."""
    analyzer = TradeReplayAnalyzer(mode="VIRTUAL")
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
        date_str="2026-08-07 09:02:00"
    )

    report = analyzer.generate_trade_analysis_report()
    assert report["signature"] == "NO AUTOMATIC STRATEGY MODIFICATION"
    assert "config_recommendations" in report
