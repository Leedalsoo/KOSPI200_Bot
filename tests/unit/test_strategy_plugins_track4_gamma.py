# -*- coding: utf-8 -*-
import numpy as np
from decimal import Decimal
from strategy.plugins.track4_gamma import SmartGammaScalpingStrategy

def test_feature_flag_seal() -> None:
    """[목표 A 검증] 설정 자산 대비 봉인(Seal) 및 활성화 경계값 대칭성 증명"""
    agent = SmartGammaScalpingStrategy({}, equity_threshold=Decimal("10000000000")) # 100억
    
    # 1. 미달 자산 (50억 ➡️ False)
    assert agent._check_feature_flag(Decimal("5000000000")) is False
    
    # 2. 정확히 임계 자산 (100억 ➡️ True)
    assert agent._check_feature_flag(Decimal("10000000000")) is True
    
    # 3. 초과 자산 (150억 ➡️ True)
    assert agent._check_feature_flag(Decimal("15000000000")) is True

def test_dynamic_deadband_range() -> None:
    """[목표 B 검증] 0.2 ~ 0.6 밴드 수축/확장 정합성 및 극단적/극초기 경계값 검증"""
    agent = SmartGammaScalpingStrategy({}, Decimal("0"))
    
    # 1. 일반적 변동성 범위 검증
    high_vals = np.array([100.0, 105.0])
    low_vals = np.array([95.0, 98.0])
    close_vals = np.array([102.0, 99.0])
    band = agent._calculate_atr_deadband(high_vals, low_vals, close_vals)
    assert Decimal("0.2") <= band <= Decimal("0.6")

    # 2. 극소 변동성 (변동성 제로 ➡️ 하한 0.2 수렴)
    high_zero = np.array([100.0, 100.0])
    low_zero = np.array([100.0, 100.0])
    close_zero = np.array([100.0, 100.0])
    band_zero = agent._calculate_atr_deadband(high_zero, low_zero, close_zero)
    assert band_zero == Decimal("0.2")

    # 3. 극대 변동성 (변동성 폭발 ➡️ 상한 0.6 클램핑)
    high_max = np.array([100.0, 1000.0])
    low_max = np.array([100.0, 10.0])
    close_max = np.array([100.0, 100.0])
    band_max = agent._calculate_atr_deadband(high_max, low_max, close_max)
    assert band_max == Decimal("0.6")

    # 4. 극초기 상태 (데이터 1개 유입 ➡️ 크래시 없이 정상 계산)
    high_init = np.array([100.0])
    low_init = np.array([90.0])
    close_init = np.array([95.0])
    band_init = agent._calculate_atr_deadband(high_init, low_init, close_init)
    assert Decimal("0.2") <= band_init <= Decimal("0.6")

def test_gamma_profit_offset() -> None:
    """[목표 C 검증] 세타 비용 대비 감마 수익 상쇄 및 동률 임계점 분기 증명"""
    agent = SmartGammaScalpingStrategy({}, Decimal("0"))
    
    # 1. 수익 > 비용 (True)
    assert agent._verify_theta_decay_offset(Decimal("1000"), Decimal("500")) is True
    
    # 2. 수익 < 비용 (False)
    assert agent._verify_theta_decay_offset(Decimal("100"), Decimal("500")) is False

    # 3. 수익 == 비용 (동률 경계값 ➡️ False)
    assert agent._verify_theta_decay_offset(Decimal("1000"), Decimal("1000")) is False
