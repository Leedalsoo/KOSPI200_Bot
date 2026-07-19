# -*- coding: utf-8 -*-
from decimal import Decimal

class MarginDietGuard:
    """브로커 마진콜 임계치 도달 여부를 통제하는 가드"""

    @staticmethod
    def calculate_margin_buffer(equity: Decimal, broker_margin: Decimal, safety_factor: Decimal) -> Decimal:
        """[목표 A] 여유 증거금 버퍼 계산 및 동적 클램핑 (음수 방지)"""
        # 안전 요구 증거금 = 브로커 마진 * (1 + safety_factor)
        # float 오염 방지를 위해 1을 Decimal('1')로 강제
        required_margin = broker_margin * (Decimal('1') + safety_factor)
        
        # 여유 버퍼 = 가용 자본 - 안전 요구 증거금
        buffer = equity - required_margin
        
        # 클램핑: 음수가 되지 않도록 max(Decimal('0'), 버퍼) 반환
        return max(Decimal('0'), buffer)

    @staticmethod
    def is_margin_critical(buffer: Decimal) -> bool:
        """[목표 B] 버퍼 고갈로 인한 마진콜 위험 상태 확인"""
        return buffer <= Decimal('0')

class ZeroLossGuard:
    """비용(수수료+슬리피지 1틱) 감안 본전 청산가 연산 가드"""

    @staticmethod
    def calculate_zero_loss_price(entry_price: Decimal, side: str, fee_rate: Decimal, tick_size: Decimal) -> Decimal:
        """[목표 C] 진입가 대비 수수료와 슬리피지를 반영한 절대 본전 탈출가 계산"""
        if side == 'BUY':
            # 롱: 본전가 = 진입가 + (진입가 * 수수료율) + 슬리피지(1틱)
            return entry_price + (entry_price * fee_rate) + tick_size
        elif side == 'SELL':
            # 숏: 본전가 = 진입가 - (진입가 * 수수료율) - 슬리피지(1틱)
            return entry_price - (entry_price * fee_rate) - tick_size
        else:
            raise ValueError(f"Invalid side: {side}. Must be 'BUY' or 'SELL'.")

    @staticmethod
    def should_liquidate(current_price: Decimal, zero_loss_price: Decimal, side: str) -> bool:
        """[목표 C] 현재가가 본전 탈출가를 붕괴시켰는지 판별 (시장가 청산 트리거)"""
        if side == 'BUY':
            # 롱: 현재가가 본전가 이하로 떨어지면 붕괴
            return current_price <= zero_loss_price
        elif side == 'SELL':
            # 숏: 현재가가 본전가 이상으로 오르면 붕괴
            return current_price >= zero_loss_price
        else:
            raise ValueError(f"Invalid side: {side}. Must be 'BUY' or 'SELL'.")
