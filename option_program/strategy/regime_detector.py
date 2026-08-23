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

    async def detect_regime(self, market_data: np.ndarray) -> Tuple[str, int]:
        """HMM 알고리즘을 통한 국면 판별 및 나노초 타임스탬프 반환"""
        self.last_update_ns = time.time_ns()

        # 🛡️ [오라클 동기화: STANDBY_OVERRIDE 상태 처리]
        if self.context.get("standby_override", False):
            self.current_regime = "NEUTRAL"
            return "NEUTRAL", self.last_update_ns

        # 빈 데이터 방어
        if market_data.size == 0:
            self.current_regime = "NEUTRAL"
            return "NEUTRAL", self.last_update_ns

        # 🛡️ [HMM 벡터 연산] 모든 파이썬 루프를 배제하고 Numpy 브로드캐스팅 및 Dot product로 전이/방출 계산
        # 1. 방출 로그 확률 행렬 연산: (T, 4) 크기의 PDF 계산
        # np.newaxis를 활용해 (T, 1) - (4,) 연산 수행
        log_emissions = -0.5 * ((market_data[:, np.newaxis] - self._means) / self._stds) ** 2 - np.log(self._stds * np.sqrt(2 * np.pi))
        
        # 2. 각 상태별 로그 확률의 합 계산 (방출 확률 누적)
        log_emissions_sum = np.sum(log_emissions, axis=0)  # (4,)

        # 언더플로우 방지를 위해 최댓값 조절 후 지수 변환 (소프트맥스 유사)
        max_log = np.max(log_emissions_sum)
        emissions = np.exp(log_emissions_sum - max_log)  # (4,)

        # 3. 전이 확률 행렬 계산 (사후 확률 계산): prior = pi * emissions, posterior = prior @ A
        prior = self._pi * emissions
        posterior = prior @ self._A

        # 4. 최대 확률을 갖는 국면 선정
        best_state = int(np.argmax(posterior))
        regimes = ["BULL", "BEAR", "SIDEWAYS", "HIGH_VOL"]
        regime_state = regimes[best_state]

        # 5. 국면 전이 시 비동기 브로드캐스트 트리거
        if regime_state != self.current_regime:
            self.current_regime = regime_state
            self._regime_event.set()
            await asyncio.sleep(0)  # 대기 중인 다른 코루틴들이 이벤트를 감지하고 깨어날 수 있도록 제어권 양보
            self._regime_event.clear()

        return self.current_regime, self.last_update_ns

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
