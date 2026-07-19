import pytest
from unittest.mock import AsyncMock
from decimal import Decimal
from datetime import datetime
import numpy as np
from core.contracts import MarketTick
from core.bus import EventPriority
from exchange.market_data import MarketDataProcessor

def test_zero_vol_clamping_protection() -> None:
    """[목표 A 검증] 1호가 잔량 합이 0일 때 OBI가 0.00으로 안전하게 귀속(Clamping)되는지 증명"""
    tick1 = MarketTick("CODE", datetime.now(), Decimal("350.00"), 0, 
                       [Decimal("0")], [Decimal("0")], 
                       [0], [0])
    bus = AsyncMock()
    processor = MarketDataProcessor(bus)
    
    mp1, obi1 = processor.calculate_microprice_and_obi(tick1)
    
    assert mp1 == Decimal("350.00")
    assert obi1 == Decimal("0")
    
    # Only Ask exists
    tick2 = MarketTick("CODE", datetime.now(), Decimal("350.00"), 0,
                       [Decimal("0")], [Decimal("351.00")],
                       [0], [10])
    mp2, obi2 = processor.calculate_microprice_and_obi(tick2)
    assert obi2 == Decimal("-1")

def test_vpin_calculation_vectorized() -> None:
    """[목표 B 검증] Numpy 배열을 이용한 VPIN 연산 정합성 증명"""
    bus = AsyncMock()
    processor = MarketDataProcessor(bus)
    
    # 임의의 buy_vol, sell_vol 행렬 주입 (shape: (n, 2))
    # [buy_vol, sell_vol]
    buckets = np.array([
        [100.0, 50.0],
        [20.0, 80.0],
        [60.0, 60.0]
    ])
    
    # VPIN 로직: sum(|buy - sell|) / sum(buy + sell)
    # |100-50| + |20-80| + |60-60| = 50 + 60 + 0 = 110
    # Total Vol = 150 + 100 + 120 = 370
    # VPIN = 110 / 370 = 0.297297...
    vpin = processor.calculate_vpin(buckets)
    assert isinstance(vpin, Decimal)
    assert round(vpin, 4) == Decimal("0.2973")

@pytest.mark.asyncio
async def test_market_halt_broadcast() -> None:
    """[목표 C 검증] 써킷브레이커 감지 시 EventBus 최상위 우선순위 브로드캐스트 증명"""
    # EventBus.publish is async, so we use AsyncMock
    bus = AsyncMock()
    processor = MarketDataProcessor(bus)
    
    await processor.check_market_halt("HALT_CODE")
    
    bus.publish.assert_called_once_with(
        EventPriority.SYSTEM, 
        "MARKET_HALT", 
        "HALT_CODE"
    )
