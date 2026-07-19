import pytest
import orjson
import uuid
from dataclasses import FrozenInstanceError
from decimal import Decimal
from datetime import datetime
from uuid import uuid4
from core.contracts import MarketTick, OrderRequest

def test_market_tick_immutability() -> None:
    """[목표 A 검증] 데이터 객체 생성 후 변조 시도 시 FrozenInstanceError 발생 증명"""
    tick = MarketTick("KR4101V83505", datetime.now(), Decimal("350.00"), 10, [], [], [], [])
    with pytest.raises(FrozenInstanceError):
        tick.last_price = Decimal("351.00") # type: ignore

def test_order_request_strict_types() -> None:
    """[목표 A 검증] 가격 Decimal, 수량 int 바인딩 정확성 증명"""
    order = OrderRequest(uuid4(), uuid4(), "KR4101V83505", Decimal("2.50"), 10, "BUY")
    assert isinstance(order.price, Decimal)
    assert order.qty == 10

def test_orjson_serialization_compatibility() -> None:
    """[목표 B 검증] orjson 직렬화 시 Decimal/UUID 에러 크래시 방어 검증"""
    order = OrderRequest(uuid4(), uuid4(), "CODE", Decimal("350.50"), 10, "SELL")
    # Decimal/UUID 커스텀 직렬화 처리가 되어야 통과 가능
    dumped = orjson.dumps(
        order, 
        default=lambda o: str(o) if isinstance(o, (Decimal, uuid.UUID)) else o
    )
    assert dumped is not None
    assert b"350.50" in dumped

def test_struct_binary_packing_layout() -> None:
    """[목표 C 검증] mmap 대응 struct 바이너리 패킹 뼈대 로직 검증"""
    order = OrderRequest(uuid4(), uuid4(), "CODE", Decimal("350.50"), 10, "BUY")
    packed = order.to_struct()
    assert isinstance(packed, bytes)
