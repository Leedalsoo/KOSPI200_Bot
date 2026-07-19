# -*- coding: utf-8 -*-
from typing import Dict, Any, cast
import numpy as np

class StrategyOrchestrator:
    """시장 국면 자율 인식 및 공유 컨텍스트 기반 가중치 오케스트레이터"""

    def __init__(self, shared_context: Dict[str, Any]) -> None:
        self.context: Dict[str, Any] = shared_context
        if "active_weights" not in self.context:
            self.context["active_weights"] = {}
        self.current_regime: int = 0  # 0: 가두리, 1: 돌파, 2: 추세

    def _run_hmm_regime_detection(self, historical_vol: np.ndarray) -> int:
        """[목표 B] Numpy 기반 초고속 변동성 임계치 분석 및 국면 판별 (0, 1, 2)"""
        # 🛡️ [Numpy NaN/Inf/빈 배열 크래시 방어]
        if historical_vol.size == 0:
            return 0
        
        # NaN 또는 Inf가 포함되어 있다면 무조건 가두리(0) 반환
        if np.isnan(historical_vol).any() or np.isinf(historical_vol).any():
            return 0

        # numpy 벡터 연산 활용 (std, mean)
        mean_val = float(np.mean(historical_vol))
        std_val = float(np.std(historical_vol))

        # 임계치 분석
        if mean_val < 0.1:
            return 0
        
        # 표준편차가 크면 급격한 국면 변화(돌파: 1)로 판정, 표준편차가 작으면 고변동 추세(추세: 2)로 판정
        if std_val > 0.5:
            return 1
        return 2

    def update_weights(self, new_weights: Dict[str, float]) -> None:
        """[목표 A] 메모리 참조 무결성을 유지하며 전략 가중치 동적 갱신"""
        # 🛡️ [메모리 참조 파괴 즉사 방어]
        # 절대 self.context["active_weights"] = new_weights 와 같이 할당하지 말 것!
        active_weights = self.context["active_weights"]
        if not isinstance(active_weights, dict):
            # 비정상 데이터 방어
            active_weights = {}
            self.context["active_weights"] = active_weights
        
        typed_weights = cast(Dict[str, float], active_weights)
        typed_weights.clear()
        typed_weights.update(new_weights)

    def rebalance_based_on_regime(self, historical_vol: np.ndarray) -> None:
        """[목표 B, C] 국면 인식 후 조건에 맞는 가중치를 생성하여 업데이트"""
        self.current_regime = self._run_hmm_regime_detection(historical_vol)

        # 국면에 따른 가중치 배분 시나리오
        if self.current_regime == 0:
            # 가두리 국면: 횡보 트랩 전략에 자본 집중
            new_weights = {
                "track2_trap": 1.0,
                "track3_arbitrage": 0.0,
                "track4_gamma": 0.0,
                "track1_defense": 0.0
            }
        elif self.current_regime == 1:
            # 돌파 국면: 아비트라지(돌파) 전략 80%, 방어 전략 20%
            new_weights = {
                "track2_trap": 0.0,
                "track3_arbitrage": 0.8,
                "track4_gamma": 0.0,
                "track1_defense": 0.2
            }
        else:
            # 추세 국면: 감마/추세 추종 전략 80%, 방어 전략 20%
            new_weights = {
                "track2_trap": 0.0,
                "track3_arbitrage": 0.0,
                "track4_gamma": 0.8,
                "track1_defense": 0.2
            }

        self.update_weights(new_weights)
