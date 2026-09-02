import math
from collections import deque
from statistics import pstdev
from typing import Optional, List
import numpy as np

from shared.contracts.canonical import CanonicalMarketTick
from option_program.strategy.regime_detector import RegimeDetector
from .market_condition_models import MarketConditionSnapshot


class MarketConditionAnalyzer:
    """CanonicalMarketTick만 관찰하여 시장상황을 계산하는 Production 분석기."""

    def __init__(
        self,
        return_window: int = 60,
        baseline_window: int = 240,
        spread_window: int = 60,
    ) -> None:
        self.return_window = max(10, return_window)
        self.baseline_window = max(self.return_window, baseline_window)
        self.prices: deque[float] = deque(maxlen=self.baseline_window + 1)
        self.spreads: deque[float] = deque(maxlen=max(10, spread_window))
        self.regime_detector = RegimeDetector()
        self.previous_price: Optional[float] = None
        self.previous_timestamp: Optional[str] = None

    @staticmethod
    def _safe_ratio(value: float, base: float) -> float:
        if base <= 0:
            return 1.0
        return max(0.0, value / base)

    def analyze(self, tick: CanonicalMarketTick) -> MarketConditionSnapshot:
        price = float(tick.underlying_price)
        bid = float(tick.bid_price or price)
        ask = float(tick.ask_price or price)
        spread = max(0.0, ask - bid)

        previous = self.previous_price
        price_change = 0.0 if previous is None else price - previous
        self.previous_price = price
        self.previous_timestamp = tick.timestamp

        self.prices.append(price)
        self.spreads.append(spread)

        returns: List[float] = []
        price_list = list(self.prices)
        for i in range(1, len(price_list)):
            p0 = price_list[i - 1]
            p1 = price_list[i]
            if p0 > 0 and p1 > 0:
                returns.append(math.log(p1 / p0))

        short_returns = returns[-self.return_window:]
        long_returns = returns[-self.baseline_window:]

        volatility = pstdev(short_returns) if len(short_returns) >= 2 else 0.0
        baseline = pstdev(long_returns) if len(long_returns) >= 2 else volatility
        ratio = self._safe_ratio(volatility, baseline)

        regime: str = "NEUTRAL"
        confidence: float = 0.0
        try:
            if len(returns) >= 2:
                regime, confidence, _ts = self.regime_detector.detect_regime_with_confidence(np.array(returns, dtype=float))
            else:
                regime, confidence = "NEUTRAL", 0.0
        except Exception:
            regime, confidence = "NEUTRAL", 0.0

        spread_baseline = pstdev(list(self.spreads)) if len(self.spreads) >= 2 else 0.0
        mean_spread = sum(self.spreads) / len(self.spreads) if self.spreads else spread
        spread_pressure = 1.0 if mean_spread <= 0 else spread / mean_spread

        liquidity_level = "NORMAL"
        if spread_pressure >= 2.5:
            liquidity_level = "THIN"
        elif spread_pressure >= 1.5:
            liquidity_level = "CAUTION"

        short_move = abs(price_change / previous) if previous else 0.0
        flash_move = short_move >= 0.005

        drawdown = 0.0
        if price_list:
            peak = max(price_list)
            if peak > 0:
                drawdown = max(0.0, (peak - price) / peak)

        gap_detected = previous is not None and short_move >= 0.01
        circuit_breaker = short_move >= 0.08

        stress = 0.0
        stress += min(1.0, max(0.0, ratio - 1.0) / 2.0) * 0.45
        stress += min(1.0, max(0.0, spread_pressure - 1.0) / 2.0) * 0.25
        stress += min(1.0, drawdown / 0.10) * 0.20
        stress += 0.10 if flash_move else 0.0
        stress = min(1.0, stress)

        flags = []
        if ratio >= 1.30:
            flags.append("VOLATILITY_SPIKE")
        if liquidity_level != "NORMAL":
            flags.append("LIQUIDITY_PRESSURE")
        if flash_move:
            flags.append("FLASH_MOVE")
        if gap_detected:
            flags.append("GAP")
        if circuit_breaker:
            flags.append("CIRCUIT_BREAKER")
        if drawdown >= 0.05:
            flags.append("DRAWDOWN")

        return MarketConditionSnapshot(
            timestamp=tick.timestamp,
            seq_id=int(tick.seq_id),
            regime=str(regime),
            regime_confidence=float(confidence),
            current_price=price,
            price_change=price_change,
            volatility=float(volatility),
            baseline_volatility=float(baseline),
            volatility_ratio=float(ratio),
            spread=float(spread),
            liquidity_level=liquidity_level,
            basis=0.0,
            oi_trend_alert=False,
            circuit_breaker=circuit_breaker,
            flash_move=flash_move,
            gap_detected=gap_detected,
            stress_level=float(stress),
            stress_flags=tuple(flags),
        )

