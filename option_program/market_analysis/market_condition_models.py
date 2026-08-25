from dataclasses import dataclass, field
from typing import Dict, Tuple

@dataclass(frozen=True)
class MarketConditionSnapshot:
    timestamp: str
    seq_id: int
    regime: str
    regime_confidence: float
    current_price: float
    price_change: float
    volatility: float
    baseline_volatility: float
    volatility_ratio: float
    spread: float
    liquidity_level: str
    basis: float
    oi_trend_alert: bool
    circuit_breaker: bool
    flash_move: bool
    gap_detected: bool
    stress_level: float
    stress_flags: Tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, object]:
        return {
            "timestamp": self.timestamp,
            "seq_id": self.seq_id,
            "regime": self.regime,
            "regime_confidence": self.regime_confidence,
            "current_price": self.current_price,
            "price_change": self.price_change,
            "volatility": self.volatility,
            "baseline_volatility": self.baseline_volatility,
            "volatility_ratio": self.volatility_ratio,
            "spread": self.spread,
            "liquidity_level": self.liquidity_level,
            "basis": self.basis,
            "oi_trend_alert": self.oi_trend_alert,
            "circuit_breaker": self.circuit_breaker,
            "flash_move": self.flash_move,
            "gap_detected": self.gap_detected,
            "stress_level": self.stress_level,
            "stress_flags": list(self.stress_flags),
        }

