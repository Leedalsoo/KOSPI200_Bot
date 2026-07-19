from decimal import Decimal
from risk.guards import MarginDietGuard, ZeroLossGuard

def test_margin_diet_evaluation_with_clamping() -> None:
    """[목표 A, B 검증] 노출 마진 비율 계산 시 동적 클램핑 및 정밀도 증명"""
    # 1000 자본, 950 증거금, 0.05 안전계수 -> 요구증거금 = 950 * 1.05 = 997.5
    # 버퍼 = 1000 - 997.5 = 2.5
    buffer_safe = MarginDietGuard.calculate_margin_buffer(Decimal('1000'), Decimal('950'), Decimal('0.05'))
    assert buffer_safe == Decimal('2.5')
    assert MarginDietGuard.is_margin_critical(buffer_safe) is False

    # 위험 상태 (클램핑 작동하여 0 반환 증명)
    # 1000 자본, 1000 증거금, 0.05 안전계수 -> 요구증거금 1050 -> 버퍼 -50 -> 0으로 클램핑
    buffer_danger = MarginDietGuard.calculate_margin_buffer(Decimal('1000'), Decimal('1000'), Decimal('0.05'))
    assert buffer_danger == Decimal('0')
    assert MarginDietGuard.is_margin_critical(buffer_danger) is True

def test_zero_loss_long_position() -> None:
    """[목표 C 검증] LONG 포지션 시 본전가 계산 및 청산 트리거 증명"""
    entry = Decimal('350.00')
    fee_rate = Decimal('0.0001') # 0.01%
    tick_size = Decimal('0.05')
    
    # 롱: 본전가 = 진입가 + (진입가 * 수수료율) + 슬리피지(1틱)
    zl_price = ZeroLossGuard.calculate_zero_loss_price(entry, 'BUY', fee_rate, tick_size)
    
    # 현재가가 본전가보다 높으면 안전
    assert ZeroLossGuard.should_liquidate(zl_price + Decimal('0.05'), zl_price, 'BUY') is False
    # 현재가가 본전가 이하면 청산
    assert ZeroLossGuard.should_liquidate(zl_price, zl_price, 'BUY') is True

def test_zero_loss_short_position() -> None:
    """[목표 C 검증] SHORT 포지션 시 본전가 계산 및 청산 트리거 증명"""
    entry = Decimal('350.00')
    fee_rate = Decimal('0.0001')
    tick_size = Decimal('0.05')
    
    # 숏: 본전가 = 진입가 - (진입가 * 수수료율) - 슬리피지(1틱)
    zl_price = ZeroLossGuard.calculate_zero_loss_price(entry, 'SELL', fee_rate, tick_size)
    
    # 현재가가 본전가보다 낮으면 안전
    assert ZeroLossGuard.should_liquidate(zl_price - Decimal('0.05'), zl_price, 'SELL') is False
    # 현재가가 본전가 이상이면 청산
    assert ZeroLossGuard.should_liquidate(zl_price, zl_price, 'SELL') is True
