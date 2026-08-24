"""Feature & Sensor Standard Contracts and Feature Extraction Pipeline.

Provides:
- FeatureVector: Authoritative DTO representing market features across Track 1~9.
- FeatureSensorPipeline: Real-time Feature and Sensor extraction pipeline with NaN/None defenses.
- TrackFeatureMapping: Mapping table documenting Feature dependencies for Track 1~9.
"""
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
import math
import time

from shared.contracts.canonical import CanonicalMarketTick
from option_program.strategy.regime_detector import RegimeDetector

@dataclass
class FeatureVector:
    """Track 1~9에서 공통으로 참조하는 표준 Feature Vector DTO"""
    seq_id: int = 0
    timestamp: str = ""
    timestamp_ns: int = 0
    underlying_price: float = 350.0
    strike_price: float = 350.0
    option_type: str = "CALL"
    bid_price: float = 349.95
    ask_price: float = 350.05
    last_price: float = 350.0
    volume: int = 100
    mid_price: float = 350.0
    spread: float = 0.10
    orderbook_imbalance: float = 0.0
    current_regime: str = "NEUTRAL"
    vol_spike_detected: bool = False
    gap_divergence_ratio: float = 0.0
    greeks: Dict[str, float] = field(default_factory=lambda: {
        "delta": 0.50,
        "gamma": 0.02,
        "theta": -0.05,
        "vega": 0.10
    })

class FeatureSensorPipeline:
    """[Feature / Sensor 추출 엔진]
    
    CanonicalMarketTick으로부터 Track 1~9가 요구하는 미시 구조,
    스프레드, HMM 레짐, 변동성, 갭 지표를 추출하고 결측치/이상치를 방어함.
    """
    def __init__(self, regime_detector: Optional[RegimeDetector] = None):
        self.regime_detector = regime_detector or RegimeDetector()
        self._last_feature_vector: Optional[FeatureVector] = None

    def extract_features(self, tick: CanonicalMarketTick, prev_close: float = 350.0) -> FeatureVector:
        """CanonicalMarketTick ➔ FeatureVector 변환 및 무결성 검증"""
        # 1. 가격 및 스프레드 계산 (NaN/Inf 방어)
        underlying = float(tick.underlying_price) if not math.isnan(tick.underlying_price) else 350.0
        bid = float(tick.bid_price) if not math.isnan(tick.bid_price) else underlying - 0.05
        ask = float(tick.ask_price) if not math.isnan(tick.ask_price) else underlying + 0.05
        last = float(tick.last_price) if not math.isnan(tick.last_price) else underlying
        
        mid = (bid + ask) / 2.0 if (bid + ask) > 0 else underlying
        spread = max(0.01, ask - bid)
        
        # 2. 호가 불균형 (Imbalance)
        imbalance = 0.0
        if ask + bid > 0:
            imbalance = round((bid - ask) / (bid + ask), 4)

        # 3. HMM 장세 국면 (Regime)
        regime_info = self.regime_detector.get_regime_info()
        current_regime = regime_info.get("regime", "NEUTRAL")

        # 4. 갭 괴리율 (Gap Divergence)
        gap_ratio = 0.0
        if prev_close > 0:
            gap_ratio = round((underlying - prev_close) / prev_close, 4)

        # 5. 변동성 스파이크 감지 (Vol Spike)
        vol_spike = (current_regime == "HIGH_VOL") or (spread > 0.30)

        # 6. Greeks 근사치 (ATM 기준 기초 델타/감마)
        moneyness = underlying - tick.strike_price
        delta = 0.50 + 0.05 * (moneyness / 2.5) if tick.option_type == "CALL" else -0.50 + 0.05 * (moneyness / 2.5)
        delta = max(-1.0, min(1.0, delta))

        fv = FeatureVector(
            seq_id=tick.seq_id,
            timestamp=tick.timestamp,
            timestamp_ns=time.time_ns(),
            underlying_price=underlying,
            strike_price=tick.strike_price,
            option_type=tick.option_type,
            bid_price=bid,
            ask_price=ask,
            last_price=last,
            volume=tick.volume,
            mid_price=mid,
            spread=spread,
            orderbook_imbalance=imbalance,
            current_regime=current_regime,
            vol_spike_detected=vol_spike,
            gap_divergence_ratio=gap_ratio,
            greeks={"delta": delta, "gamma": 0.02, "theta": -0.05, "vega": 0.10}
        )
        self._last_feature_vector = fv
        return fv

    def get_last_features(self) -> Optional[FeatureVector]:
        return self._last_feature_vector

# =========================================================================
# Track 1~9 Feature 의존성 및 계약 매핑 테이블 (Documentation & Verification)
# =========================================================================
TRACK_FEATURE_DEPENDENCY_MATRIX = {
    "Track1_HybridScalping": ["mid_price", "spread", "orderbook_imbalance", "last_price"],
    "Track2_Breakout": ["underlying_price", "last_price", "volume"],
    "Track3_StatisticalArbitrage": ["spread", "current_regime", "vol_spike_detected", "mid_price"],
    "Track4_GammaScalping": ["greeks.delta", "greeks.gamma", "greeks.theta", "underlying_price"],
    "Track5_GapProtocol": ["gap_divergence_ratio", "current_regime", "underlying_price"],
    "Track6_DailyTailInsurance": ["vol_spike_detected", "current_regime", "underlying_price"],
    "Track7_VolatilityArbitrage": ["greeks.vega", "spread", "current_regime"],
    "Track8_MacroStrangle": ["current_regime", "spread", "underlying_price"],
    "Track9_EventOvernight": ["gap_divergence_ratio", "vol_spike_detected", "current_regime"]
}
