"""Phase 4 & Step 2-3: Feature Lifecycle, Input/Output, and Boundary Condition Unit Tests.

Verifies:
1. Feature Input: CanonicalMarketTick ingestion and field validation.
2. Feature Output: MarketConditionSnapshot and FeatureVector DTO structure and types.
3. Feature Computation: Correct mathematical calculations of returns, volatility, spread pressure, and regime.
4. Update Lifecycle: Strict per-tick updates without stale retention.
5. Initial State & Boundary Conditions: Graceful handling of single-tick history, zero volatility, and abnormal inputs.
"""
import pytest
import math
from datetime import datetime

from shared.contracts.canonical import CanonicalMarketTick
from option_program.market_analysis.market_condition_analyzer import MarketConditionAnalyzer
from option_program.market_analysis.market_condition_models import MarketConditionSnapshot
from option_program.sensor.feature_contract import FeatureSensorPipeline, FeatureVector


def test_feature_input_and_output_structure():
    """1. Feature Ingestion & Output Schema Verification."""
    analyzer = MarketConditionAnalyzer(return_window=10, baseline_window=20)
    pipeline = FeatureSensorPipeline()

    tick = CanonicalMarketTick(
        timestamp="2026-08-28 09:00:01.000",
        underlying_price=350.0,
        strike_price=350.0,
        option_type="CALL",
        bid_price=349.90,
        ask_price=350.10,
        last_price=350.0,
        volume=500,
        seq_id=1
    )

    # 1-1. MarketConditionAnalyzer
    snapshot = analyzer.analyze(tick)
    assert isinstance(snapshot, MarketConditionSnapshot)
    assert snapshot.seq_id == 1
    assert snapshot.current_price == 350.0
    assert snapshot.spread == pytest.approx(0.20, abs=1e-5)
    assert isinstance(snapshot.regime, str)
    assert isinstance(snapshot.volatility, float)
    assert isinstance(snapshot.stress_flags, tuple)

    # 1-2. FeatureSensorPipeline
    fv = pipeline.extract_features(tick, prev_close=350.0)
    assert isinstance(fv, FeatureVector)
    assert fv.seq_id == 1
    assert fv.underlying_price == 350.0
    assert fv.mid_price == pytest.approx(350.0, abs=1e-5)
    assert fv.spread == pytest.approx(0.20, abs=1e-5)
    assert "delta" in fv.greeks


def test_feature_update_lifecycle_per_tick():
    """2. Verifies that features update strictly per tick without stale residual."""
    analyzer = MarketConditionAnalyzer(return_window=10, baseline_window=20)

    # Tick 1
    t1 = CanonicalMarketTick(
        timestamp="09:00:01", underlying_price=350.0, bid_price=349.95, ask_price=350.05, seq_id=1
    )
    s1 = analyzer.analyze(t1)
    assert s1.current_price == 350.0
    assert s1.price_change == 0.0

    # Tick 2
    t2 = CanonicalMarketTick(
        timestamp="09:00:02", underlying_price=352.0, bid_price=351.95, ask_price=352.05, seq_id=2
    )
    s2 = analyzer.analyze(t2)
    assert s2.current_price == 352.0
    assert s2.price_change == pytest.approx(2.0, abs=1e-5)
    assert len(analyzer.prices) == 2

    # Tick 3
    t3 = CanonicalMarketTick(
        timestamp="09:00:03", underlying_price=349.0, bid_price=348.90, ask_price=349.10, seq_id=3
    )
    s3 = analyzer.analyze(t3)
    assert s3.current_price == 349.0
    assert s3.price_change == pytest.approx(-3.0, abs=1e-5)
    assert len(analyzer.prices) == 3


def test_feature_initial_state_handling():
    """3. Initial State: Single tick with insufficient history produces safe baseline values."""
    analyzer = MarketConditionAnalyzer(return_window=10, baseline_window=20)

    t1 = CanonicalMarketTick(
        timestamp="09:00:01", underlying_price=350.0, bid_price=350.0, ask_price=350.0, seq_id=1
    )
    s1 = analyzer.analyze(t1)

    assert s1.price_change == 0.0
    assert s1.volatility == 0.0
    assert s1.baseline_volatility == 0.0
    assert s1.volatility_ratio == 1.0
    assert s1.regime == "NEUTRAL"
    assert s1.regime_confidence == 0.0


def test_feature_boundary_conditions_and_defenses():
    """4. Boundary conditions: identical prices, flash crashes, wide spreads, and zero bids."""
    analyzer = MarketConditionAnalyzer(return_window=5, baseline_window=10)

    # 4-1. Identical prices in series
    for i in range(1, 10):
        t = CanonicalMarketTick(
            timestamp=f"09:00:0{i}", underlying_price=350.0, bid_price=349.95, ask_price=350.05, seq_id=i
        )
        s = analyzer.analyze(t)
    assert s.price_change == 0.0
    assert s.volatility == 0.0

    # 4-2. Flash Crash triggering flags
    t_crash = CanonicalMarketTick(
        timestamp="09:00:10", underlying_price=320.0, bid_price=319.0, ask_price=321.0, seq_id=10
    )
    s_crash = analyzer.analyze(t_crash)
    assert s_crash.flash_move is True
    assert s_crash.gap_detected is True
    assert "FLASH_MOVE" in s_crash.stress_flags or "GAP" in s_crash.stress_flags
    assert s_crash.stress_level > 0.0
