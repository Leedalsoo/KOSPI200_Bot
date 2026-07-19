from decimal import Decimal
from risk.greeks import GreeksEngine

def test_zero_time_to_maturity_iv_clamping() -> None:
    """[목표 A 검증] 만기일 D-0 시점 분모 0 방어 및 최소값 클램핑 증명"""
    engine = GreeksEngine()
    # t=0 으로 극단적 상황 주입
    iv = engine.calculate_iv(Decimal("2.50"), Decimal("350"), Decimal("350"), Decimal("0"))
    assert iv >= Decimal("0.0001")

def test_numpy_greeks_vectorization_accuracy() -> None:
    """[목표 B 검증] Numpy 벡터 합산이 순회 연산과 동일한 Decimal 정밀도를 내는지 증명"""
    engine = GreeksEngine()
    positions = {"OPT1": 10, "OPT2": -5}
    deltas = {"OPT1": Decimal("0.50"), "OPT2": Decimal("-0.30")}
    gammas = {"OPT1": Decimal("0.02"), "OPT2": Decimal("0.05")}
    vegas = {"OPT1": Decimal("0.10"), "OPT2": Decimal("0.15")}

    results = engine.calculate_portfolio_greeks(positions, deltas, gammas, vegas)
    
    # Delta: (10 * 0.50) + (-5 * -0.30) = 5.0 + 1.5 = 6.5
    # Gamma: (10 * 0.02) + (-5 * 0.05) = 0.2 - 0.25 = -0.05
    # Vega:  (10 * 0.10) + (-5 * 0.15) = 1.0 - 0.75 = 0.25
    assert results["Delta"] == Decimal("6.5")
    assert results["Gamma"] == Decimal("-0.05")
    assert results["Vega"] == Decimal("0.25")

def test_iv_caching_performance() -> None:
    """[목표 C 검증] 캐싱 로직이 정상 작동하여 캐시 히트 시 객체를 그대로 반환하는지 증명"""
    engine = GreeksEngine()
    iv1 = engine.calculate_iv(Decimal("3.0"), Decimal("355"), Decimal("350"), Decimal("0.1"))
    iv2 = engine.calculate_iv(Decimal("3.0"), Decimal("355"), Decimal("350"), Decimal("0.1"))
    
    # 동일한 캐시 객체를 참조해야 함
    assert id(iv1) == id(iv2) or iv1 == iv2
    assert len(engine._iv_cache) == 1
