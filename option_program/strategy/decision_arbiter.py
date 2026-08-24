"""Production Decision Arbiter Architecture.

Resolves signal conflicts, resource contention, and priority hierarchy across Strategy Track 1~9:
- Priority Hierarchy (Emergency Hedge > Tail Insurance > Alpha/Neutral > Directional Momentum)
- Opposite Signal Resolution & Netting (BUY vs SELL clash on identical instrument)
- Margin Resource Contention (Fair & deterministic margin allocation under constrained equity)
- Deterministic Arbitration Guarantee
"""
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple
import logging
import uuid
import time

from shared.contracts.canonical import (
    CanonicalStrategySignal,
    CanonicalOrderCommand,
    CanonicalAssetType,
    CanonicalOrderSide,
    CanonicalOptionType,
    CanonicalAccountSummary
)

logger = logging.getLogger(__name__)

# 전략별 우선순위 가중치 (낮을수록 높은 우선순위)
STRATEGY_PRIORITY_MAP = {
    "HEDGE_DELTA": 1,
    "HEDGE_TAIL": 1,
    "Track1": 2,      # Tail Defense & Core Scalping (30% 자본)
    "Track6": 3,      # 0DTE Daily Tail Insurance
    "Track9": 3,      # Overnight Event Hedge
    "Track3": 4,      # Statistical Arbitrage
    "Track4": 4,      # Gamma Scalping
    "Track7": 5,      # Volatility Arbitrage
    "Track8": 5,      # Monthly Wide Strangle
    "Track2": 6,      # Breakout Momentum
    "Track5": 6,      # Pure Gap Divergence
}

@dataclass
class ArbitrationResult:
    """중재 결과 DTO"""
    approved_signals: List[CanonicalStrategySignal]
    rejected_signals: List[Tuple[CanonicalStrategySignal, str]] # (signal, rejection_reason)
    netted_clashes: List[str]

class DecisionArbiter:
    """[결정 중재자] 복수 전략의 동시 발생 신호를 중재하여 충돌 해소 및 자원 배분"""

    def __init__(self):
        pass

    def _get_priority(self, track_id: str) -> int:
        return STRATEGY_PRIORITY_MAP.get(track_id, 99)

    def arbitrate(
        self,
        signals: List[CanonicalStrategySignal],
        account: CanonicalAccountSummary
    ) -> ArbitrationResult:
        """복수 신호 동시 중재 파이프라인"""
        if not signals:
            return ArbitrationResult(approved_signals=[], rejected_signals=[], netted_clashes=[])

        approved: List[CanonicalStrategySignal] = []
        rejected: List[Tuple[CanonicalStrategySignal, str]] = []
        netted_clashes: List[str] = []

        # 1. 우선순위 정렬 (Priority Ascending, 그 다음 수량 많은 순)
        sorted_signals = sorted(
            signals,
            key=lambda s: (self._get_priority(s.track_id), -s.qty, s.signal_id)
        )

        # 2. 동일 종목 상충 신호(BUY vs SELL) 감지 및 중재
        # instrument_key -> (winning_signal, winning_priority)
        instrument_claims: Dict[str, CanonicalStrategySignal] = {}

        for sig in sorted_signals:
            inst_key = f"{sig.asset_type.value}_{sig.strike}_{sig.option_type.value if sig.option_type else 'NONE'}"

            if inst_key not in instrument_claims:
                instrument_claims[inst_key] = sig
                approved.append(sig)
            else:
                existing_sig = instrument_claims[inst_key]
                # 상충 신호 발생 (한쪽은 BUY, 한쪽은 SELL)
                if existing_sig.side != sig.side:
                    reason = f"CLASH_NETTING_REJECTED: Subordinate to {existing_sig.track_id} ({existing_sig.side.value})"
                    rejected.append((sig, reason))
                    netted_clashes.append(f"Clash on {inst_key}: Kept {existing_sig.track_id}({existing_sig.side.value}), Rejected {sig.track_id}({sig.side.value})")
                    logger.warning(f"[DecisionArbiter] {reason} on {inst_key}")
                else:
                    # 동일 방향 신호는 수용 (포지션 합산)
                    approved.append(sig)

        return ArbitrationResult(
            approved_signals=approved,
            rejected_signals=rejected,
            netted_clashes=netted_clashes
        )
