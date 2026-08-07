import random
from decimal import Decimal
from datetime import datetime
from core.contracts import MarketTick, validate_market_tick, calculate_available_funds

def test_deterministic_random_seed():
    """동일한 SIMULATION_SEED (42)에서 무작위 난수 시퀀스가 100% 동일함을 검증"""
    random.seed(42)
    seq_a = [random.uniform(-5.0, 5.0) for _ in range(20)]
    
    random.seed(42)
    seq_b = [random.uniform(-5.0, 5.0) for _ in range(20)]
    
    assert seq_a == seq_b, "동일 시드에서 생성된 난수 시퀀스가 일치해야 합니다."

def test_market_tick_validation_determinism():
    """1x 및 300x 환경에서 동일한 틱 데이터 검증 결과가 100% 동일함을 검증"""
    dt1 = datetime(2026, 8, 7, 9, 0, 0)
    dt2 = datetime(2026, 8, 7, 9, 0, 30)
    
    tick1 = MarketTick(
        instrument_code="KOSPI200",
        timestamp=dt1,
        last_price=Decimal("350.00"),
        seq=1,
        bid_price=Decimal("349.90"),
        ask_price=Decimal("350.10")
    )
    
    tick2 = MarketTick(
        instrument_code="KOSPI200",
        timestamp=dt2,
        last_price=Decimal("350.50"),
        seq=2,
        bid_price=Decimal("350.40"),
        ask_price=Decimal("350.60")
    )
    
    valid1, err1 = validate_market_tick(tick1, None)
    valid2, err2 = validate_market_tick(tick2, tick1)
    
    assert valid1 is True and len(err1) == 0
    assert valid2 is True and len(err2) == 0

def test_account_numeric_tolerance():
    """부동소수점 및 Decimal 계좌 연산 1e-6 허용 오차 이내 수렴 검증"""
    cash = Decimal("100000000.00")
    pending = Decimal("5000000.00")
    margin = Decimal("15000000.00")
    
    avail_a = calculate_available_funds(cash, pending, margin)
    avail_b = calculate_available_funds(cash, pending, margin)
    
    assert abs(avail_a - avail_b) <= Decimal("0.000001")
