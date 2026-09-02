import numpy as np
import pytest
from option_program.strategy.regime_detector import RegimeDetector
from option_program.market_analysis.market_condition_analyzer import MarketConditionAnalyzer
from shared.contracts.canonical import CanonicalMarketTick


def test_regime_detector_posterior_confidence_calculation():
    """HMM 국면 탐지 시 사후확률(confidence)이 0.0~1.0 범위로 정확히 산출되는지 검증."""
    detector = RegimeDetector()
    returns = np.array([0.006, 0.005, 0.007, 0.004, 0.008], dtype=float)

    regime, confidence, ts = detector.detect_regime_with_confidence(returns)
    assert regime in ["BULL", "BEAR", "SIDEWAYS", "HIGH_VOL", "NEUTRAL"]
    assert isinstance(confidence, float)
    assert 0.0 <= confidence <= 1.0
    assert confidence > 0.5  # 강한 상승 추세 시 높은 신뢰도
    assert ts > 0

    # 기존 detect_regime_sync 계약(Tuple[str, int]) 호환성 검증
    sync_regime, sync_ts = detector.detect_regime_sync(returns)
    assert sync_regime == regime
    assert sync_ts > 0
    assert detector.last_confidence == confidence


def test_market_condition_analyzer_preserves_regime_confidence():
    """MarketConditionAnalyzer가 틱 분석 시 실제 HMM confidence를 온전히 보존하는지 검증."""
    analyzer = MarketConditionAnalyzer(return_window=5, baseline_window=10)

    # 틱 순차 유입
    prices = [350.0, 350.5, 351.2, 352.0, 353.1, 354.5]
    last_snapshot = None
    for i, p in enumerate(prices):
        tick = CanonicalMarketTick(
            timestamp=f"2026-09-02 09:00:0{i}.000",
            underlying_price=p,
            strike_price=350.0,
            option_type="CALL",
            bid_price=p - 0.1,
            ask_price=p + 0.1,
            last_price=p,
            volume=100,
            seq_id=i + 1
        )
        last_snapshot = analyzer.analyze(tick)

    assert last_snapshot is not None
    assert isinstance(last_snapshot.regime_confidence, float)
    assert 0.0 <= last_snapshot.regime_confidence <= 1.0
    assert last_snapshot.regime_confidence > 0.0
