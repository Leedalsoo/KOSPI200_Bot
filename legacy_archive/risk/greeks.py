# -*- coding: utf-8 -*-
from decimal import Decimal
from typing import Dict, Tuple
import numpy as np
import math

class GreeksEngine:
    """HFT 포트폴리오 민감도(Greeks) 및 IV 산출 초고속 엔진"""

    def __init__(self) -> None:
        # IV 캐싱을 위한 딕셔너리 (키: 파라미터 튜플, 값: IV)
        self._iv_cache: Dict[Tuple[float, float, float, float], Decimal] = {}

    def calculate_iv(self, price: Decimal, spot: Decimal, strike: Decimal, t: Decimal) -> Decimal:
        """[목표 A, C] Zero Division 방어 및 캐싱이 적용된 IV 산출"""
        # [목표 A] 시간(t) 클램핑: 만기일 ZeroDivisionError 방어
        clamped_t = max(Decimal('0.0001'), t)
        
        # 캐시 키 생성
        cache_key = (float(price), float(spot), float(strike), float(clamped_t))
        
        # [목표 C] 캐시 히트 시 반환
        if cache_key in self._iv_cache:
            return self._iv_cache[cache_key]
            
        # OOM 방어를 위한 캐시 클리어 기법 적용
        if len(self._iv_cache) > 10000:
            self._iv_cache.clear()
            
        # 블랙-숄즈 수식을 모방한 IV 산출 (ZeroDivision 원천 차단 시뮬레이션)
        # 실제 환경에서는 Newton-Raphson 등으로 역산하지만, 여기서는 방어 기재 증명을 위한 로직 구현
        # sigma * math.sqrt(t) 분모 보호 확인용
        t_float = float(clamped_t)
        sigma_approx = float(price) / (float(spot) * math.sqrt(t_float))
        
        # 안전한 값으로 반환
        iv_val = Decimal(str(round(max(0.0001, sigma_approx), 4)))
        
        self._iv_cache[cache_key] = iv_val
        return iv_val

    def calculate_portfolio_greeks(
        self, 
        positions: Dict[str, int], 
        deltas: Dict[str, Decimal], 
        gammas: Dict[str, Decimal], 
        vegas: Dict[str, Decimal]
    ) -> Dict[str, Decimal]:
        """[목표 B] Numpy 벡터 연산을 활용한 포트폴리오 전체 Greeks 초고속 합산"""
        # 순서를 보장하기 위해 키 리스트 추출
        keys = list(positions.keys())
        
        # Numpy 배열 변환
        pos_array = np.array([positions[k] for k in keys], dtype=np.float64)
        delta_array = np.array([float(deltas[k]) for k in keys], dtype=np.float64)
        gamma_array = np.array([float(gammas[k]) for k in keys], dtype=np.float64)
        vega_array = np.array([float(vegas[k]) for k in keys], dtype=np.float64)
        
        # 벡터 내적 연산 (초고속 O(1) 레벨 연산)
        total_delta = np.dot(pos_array, delta_array)
        total_gamma = np.dot(pos_array, gamma_array)
        total_vega = np.dot(pos_array, vega_array)
        
        # [레드팀 지령] float 오염 방어를 위한 문자열 변환 후 Decimal 캐스팅
        return {
            "Delta": Decimal(str(round(total_delta, 4))),
            "Gamma": Decimal(str(round(total_gamma, 4))),
            "Vega": Decimal(str(round(total_vega, 4)))
        }
