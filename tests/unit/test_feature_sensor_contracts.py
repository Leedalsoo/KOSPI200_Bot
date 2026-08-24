"""Unit Test: Feature & Sensor Contracts, Extraction Pipeline & Track 1~9 Dependencies."""
import pytest
import math
import numpy as np

from shared.contracts.canonical import CanonicalMarketTick
from option_program.strategy.regime_detector import RegimeDetector
from option_program.sensor.feature_contract import (
    FeatureVector,
    FeatureSensorPipeline,
    TRACK_FEATURE_DEPENDENCY_MATRIX
)

def test_feature_vector_extraction_and_invariants():
    """Validates that FeatureSensorPipeline correctly extracts all Feature fields from CanonicalMarketTick."""
    pipeline = FeatureSensorPipeline()
    tick = CanonicalMarketTick(
        seq_id=100,
        timestamp="09:00:01.234",
        underlying_price=350.0,
        strike_price=350.0,
        option_type="CALL",
        bid_price=349.90,
        ask_price=350.10,
        last_price=350.05,
        volume=500
    )

    fv = pipeline.extract_features(tick, prev_close=348.0)
    assert isinstance(fv, FeatureVector)
    assert fv.seq_id == 100
    assert fv.underlying_price == 350.0
    assert fv.mid_price == 350.00
    assert round(fv.spread, 2) == 0.20
    assert fv.current_regime in ["NEUTRAL", "BULL", "BEAR", "SIDEWAYS", "HIGH_VOL"]
    assert fv.gap_divergence_ratio > 0  # (350 - 348) / 348 > 0
    assert "delta" in fv.greeks
    assert "gamma" in fv.greeks
    assert "theta" in fv.greeks
    assert "vega" in fv.greeks

def test_nan_and_corrupted_tick_defenses():
    """Validates that NaN or corrupted inputs in MarketTick are safely defended without NaN propagation."""
    pipeline = FeatureSensorPipeline()
    tick_corrupted = CanonicalMarketTick(
        seq_id=101,
        timestamp="09:00:02.000",
        underlying_price=float("nan"),
        strike_price=350.0,
        option_type="CALL",
        bid_price=float("nan"),
        ask_price=float("nan"),
        last_price=float("nan"),
        volume=0
    )

    fv = pipeline.extract_features(tick_corrupted)
    assert not math.isnan(fv.underlying_price)
    assert not math.isnan(fv.bid_price)
    assert not math.isnan(fv.ask_price)
    assert not math.isnan(fv.mid_price)
    assert not math.isnan(fv.spread)

def test_regime_integration_and_vol_spike():
    """Validates RegimeDetector HMM vectorization integration and Vol Spike detection."""
    regime_detector = RegimeDetector()
    # Feed high volatility returns
    high_vol_data = np.array([0.02, -0.025, 0.03, -0.02, 0.025])
    regime_state, _ = regime_detector.detect_regime_sync(high_vol_data)
    assert regime_state == "HIGH_VOL"

    pipeline = FeatureSensorPipeline(regime_detector=regime_detector)
    tick = CanonicalMarketTick(
        seq_id=102,
        timestamp="09:00:03.000",
        underlying_price=350.0,
        strike_price=350.0,
        option_type="CALL",
        bid_price=349.50,
        ask_price=350.50,
        last_price=350.0,
        volume=100
    )
    fv = pipeline.extract_features(tick)
    assert fv.current_regime == "HIGH_VOL"
    assert fv.vol_spike_detected is True

def test_track_1_to_9_feature_dependency_matrix_completeness():
    """Validates that all 9 Strategy Tracks have 100% complete and valid Feature dependencies."""
    pipeline = FeatureSensorPipeline()
    sample_tick = CanonicalMarketTick(
        seq_id=1, timestamp="09:00:00.000", underlying_price=350.0,
        strike_price=350.0, option_type="CALL", bid_price=349.95,
        ask_price=350.05, last_price=350.0, volume=100
    )
    fv = pipeline.extract_features(sample_tick)

    # Verify all 9 tracks are defined
    assert len(TRACK_FEATURE_DEPENDENCY_MATRIX) == 9

    # Verify every required feature exists on FeatureVector
    for track_name, req_features in TRACK_FEATURE_DEPENDENCY_MATRIX.items():
        assert len(req_features) > 0, f"{track_name} has empty feature requirements"
        for feat in req_features:
            if "." in feat:
                parent, child = feat.split(".", 1)
                assert hasattr(fv, parent), f"{track_name} missing parent feature '{parent}'"
                parent_val = getattr(fv, parent)
                assert child in parent_val, f"{track_name} missing sub-feature '{child}' in '{parent}'"
            else:
                assert hasattr(fv, feat), f"{track_name} missing required feature '{feat}' on FeatureVector"
