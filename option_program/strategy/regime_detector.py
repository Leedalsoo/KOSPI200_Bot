# -*- coding: utf-8 -*-
import numpy as np
import asyncio
import time
from typing import Tuple, Dict, Any, Optional

class RegimeDetector:
    """HMM 기반 시장 국면 자율 인식 엔진"""

    def __init__(self, shared_context: Optional[Dict[str, Any]] = None) -> None:
        self.context: Dict[str, Any] = shared_context if shared_context is not None else {}
        self.current_regime: str = "NEUTRAL"
        self._regime_event: asyncio.Event = asyncio.Event()
        self.last_update_ns: int = 0
        self.last_confidence: float = 0.0
        self.embargo_ns: int = 1_000_000_000  # 🛡️ 엠바고 기간: 1초 (나노초 단위)

        # HMM 가우시안 방출 파라미터 (상태 순서: BULL, BEAR, SIDEWAYS, HIGH_VOL)
        self._means: np.ndarray = np.array([0.005, -0.005, 0.000, 0.000])
        self._stds: np.ndarray = np.array([0.003, 0.005, 0.001, 0.015])

        # 초기 상태 확률 pi
        self._pi: np.ndarray = np.array([0.25, 0.25, 0.25, 0.25])

        # 전이 확률 행렬 A (대각 성분이 높은 안정적 국면 전이 모델)
        self._A: np.ndarray = np.array([
            [0.7, 0.1, 0.1, 0.1],  # BULL -> BULL, BEAR, SIDEWAYS, HIGH_VOL
            [0.1, 0.7, 0.1, 0.1],  # BEAR -> ...
            [0.1, 0.1, 0.7, 0.1],  # SIDEWAYS -> ...
            [0.1, 0.1, 0.1, 0.7]   # HIGH_VOL -> ...
        ])

    def detect_regime_sync(self, market_data: np.ndarray) -> Tuple[str, int]:
        """[동기식 HMM 연산] 시장 시계열(수익률)을 입력받아 HMM 벡터 연산으로 국면 판별"""
        self.last_update_ns = time.time_ns()

        if self.context.get("standby_override", False) or market_data.size == 0:
            self.current_regime = "NEUTRAL"
            self.last_confidence = 0.0
            return "NEUTRAL", self.last_update_ns

        # HMM 벡터 연산
        log_emissions = -0.5 * ((market_data[:, np.newaxis] - self._means) / self._stds) ** 2 - np.log(self._stds * np.sqrt(2 * np.pi))
        log_emissions_sum = np.sum(log_emissions, axis=0)
        max_log = np.max(log_emissions_sum)
        emissions = np.exp(log_emissions_sum - max_log)

        prior = self._pi * emissions
        posterior = prior @ self._A

        post_sum = float(np.sum(posterior))
        best_state = int(np.argmax(posterior))
        if post_sum > 0:
            norm_posterior = posterior / post_sum
            self.last_confidence = float(norm_posterior[best_state])
        else:
            self.last_confidence = 0.0

        regimes = ["BULL", "BEAR", "SIDEWAYS", "HIGH_VOL"]
        self.current_regime = regimes[best_state]
        return self.current_regime, self.last_update_ns

    def detect_regime_with_confidence(self, market_data: np.ndarray) -> Tuple[str, float, int]:
        """[동기식 HMM 연산] 시장 시계열(수익률)을 입력받아 (국면, 신뢰도 사후확률, 나노초 타임스탬프) 반환"""
        regime, ts = self.detect_regime_sync(market_data)
        return regime, self.last_confidence, ts

    async def detect_regime(self, market_data: np.ndarray) -> Tuple[str, int]:
        """HMM 알고리즘을 통한 비동기 국면 판별 및 나노초 타임스탬프 반환"""
        regime_state, ts = self.detect_regime_sync(market_data)
        if self._regime_event.is_set():
            self._regime_event.clear()
        return regime_state, ts

    def get_regime_info(self, current_time_ns: Optional[int] = None) -> Dict[str, Any]:
        """전략 플러그인을 위한 국면 상태 보고 (Purged CV 및 엠바고 룰 반영)"""
        # 🛡️ [가상-미래 참조 금지] 백테스트 엔진 등에서 미래 참조를 시도할 경우 차단
        if current_time_ns is not None:
            # 엠바고 시간(last_update_ns + embargo_ns)을 만족하지 못하면 임시 중립 상태 반환
            if current_time_ns < self.last_update_ns + self.embargo_ns:
                return {
                    "regime": "NEUTRAL",
                    "timestamp_ns": self.last_update_ns,
                    "embargo_active": True
                }

        return {
            "regime": self.current_regime,
            "timestamp_ns": self.last_update_ns,
            "embargo_active": False
        }
