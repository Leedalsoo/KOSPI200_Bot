# -*- coding: utf-8 -*-
from decimal import Decimal
from typing import List, Dict
from collections import deque
import numpy as np
import logging
from core.contracts import ExecutionReport

logger = logging.getLogger(__name__)

class SensorAnalyzer:
    """비간섭 미시 슬리피지 분석기 (Memory-efficient Slotted Window)"""
    
    def __init__(self, window_size: int = 1000) -> None:
        self.window_size: int = window_size
        self._slippage_history: deque[Decimal] = deque(maxlen=window_size)

    def analyze_slippage(self, reports: List[ExecutionReport], order_prices: Dict[str, Decimal]) -> Decimal:
        """[목표 A, B] Deque 기반 메모리 보존 및 Numpy 벡터 연산을 통한 정밀 슬리피지 평균 산출"""
        # 🛡️ [조용한 OOM 방어] 수십만 건 유입에 대비하여 처리량을 1000건으로 강제 슬라이싱 제한
        valid_reports = reports[:1000]

        for r in valid_reports:
            broker_id = r.broker_order_id
            if broker_id not in order_prices:
                continue

            fill_price = r.filled_price
            order_price = order_prices[broker_id]

            # 🛡️ [정수/소수 혼용 주의] 타입 체크 후 Decimal로 통일 표준화
            if not isinstance(fill_price, Decimal):
                logger.debug("Normalizing non-Decimal filled_price: %s", fill_price)
                fill_price = Decimal(str(fill_price))

            if not isinstance(order_price, Decimal):
                logger.debug("Normalizing non-Decimal order_price: %s", order_price)
                order_price = Decimal(str(order_price))

            # 슬리피지 편차 절댓값 계산
            slippage = abs(fill_price - order_price)
            self._slippage_history.append(slippage)

        if not self._slippage_history:
            return Decimal("0")

        # Numpy 가속 연산
        arr = np.array([float(x) for x in self._slippage_history])
        mean_val = np.mean(arr)

        # 🛡️ [Numpy Float 오염 방어] float64를 소수 4자리 반올림 후 Decimal로 변환하여 정밀도 유지
        return Decimal(str(np.round(mean_val, 4)))

    def get_slippage_stats(self) -> Dict[str, Decimal]:
        """[목표 B] 슬리피지 표준편차 등 통계 정보 반환"""
        if not self._slippage_history:
            return {"mean": Decimal("0"), "std": Decimal("0")}

        arr = np.array([float(x) for x in self._slippage_history])
        mean_val = np.mean(arr)
        std_val = np.std(arr)

        # 🛡️ [Numpy Float 오염 방어]
        return {
            "mean": Decimal(str(np.round(mean_val, 4))),
            "std": Decimal(str(np.round(std_val, 4)))
        }
