import pytest
import time
from decimal import Decimal
from uuid import uuid4

from core.contracts import OrderRequest, OrderStatus, RiskApprovalToken
from core.bus import EventBus
from fsm.oms_fsm import OmsFsm
from risk.risk_manager import RiskManager

@pytest.mark.asyncio
async def test_fat_finger_pricing_block() -> None:
    """[목표 A, B 검증] Fat-Finger 가격 입력 시 검증 실패 및 FSM REJECTED 전이 증명"""
    bus = EventBus()
    fsm = OmsFsm()
    manager = RiskManager(bus, fsm, max_qty=100, max_deviation_pct=Decimal("0.10"))
    
    oid = uuid4()
    # Mock token for registration
    token = RiskApprovalToken(oid, time.time_ns(), "mock_sig")
    await fsm.register_order(token)
    
    # BBO가 350.00 인데 400.00 에 주문 (10% 초과)
    req = OrderRequest(uuid4(), oid, "CODE", Decimal("400.00"), 10, "BUY")
    result_token = await manager.validate_order(req, Decimal("350.00"))
    
    assert result_token is None
    assert fsm.get_status(oid) == OrderStatus.REJECTED

@pytest.mark.asyncio
async def test_max_qty_block() -> None:
    """[목표 A 검증] 수량 한도 초과 시 즉각 차단 증명"""
    bus = EventBus()
    fsm = OmsFsm()
    manager = RiskManager(bus, fsm, max_qty=100, max_deviation_pct=Decimal("0.10"))
    
    oid = uuid4()
    token = RiskApprovalToken(oid, time.time_ns(), "mock_sig")
    await fsm.register_order(token)
    
    # 정상 가격이나, 수량이 101로 초과
    req = OrderRequest(uuid4(), oid, "CODE", Decimal("350.00"), 101, "BUY")
    result_token = await manager.validate_order(req, Decimal("350.00"))
    
    assert result_token is None
    assert fsm.get_status(oid) == OrderStatus.REJECTED

@pytest.mark.asyncio
async def test_vpin_filter_block() -> None:
    """[하이브리드 검증] VPIN 초과 시 즉각 차단 증명"""
    bus = EventBus()
    fsm = OmsFsm()
    manager = RiskManager(bus, fsm, max_qty=100, max_deviation_pct=Decimal("0.10"))
    
    oid = uuid4()
    token = RiskApprovalToken(oid, time.time_ns(), "mock_sig")
    await fsm.register_order(token)
    
    # 정상 주문이지만 VPIN이 0.9로 초과 (Threshold 0.8)
    req = OrderRequest(uuid4(), oid, "CODE", Decimal("350.00"), 10, "BUY")
    result_token = await manager.validate_order(req, Decimal("350.00"), current_vpin=Decimal("0.9"))
    
    assert result_token is None
    assert fsm.get_status(oid) == OrderStatus.REJECTED

@pytest.mark.asyncio
async def test_latency_check_block() -> None:
    """[하이브리드 검증] Latency 지연 발생 시 차단 증명"""
    bus = EventBus()
    fsm = OmsFsm()
    manager = RiskManager(bus, fsm, max_qty=100, max_deviation_pct=Decimal("0.10"))
    
    oid = uuid4()
    token = RiskApprovalToken(oid, time.time_ns(), "mock_sig")
    await fsm.register_order(token)
    
    # 20ms 이전의 타임스탬프 세팅
    old_timestamp = time.time_ns() - 20_000_000
    req = OrderRequest(uuid4(), oid, "CODE", Decimal("350.00"), 10, "BUY", timestamp_ns=old_timestamp)
    result_token = await manager.validate_order(req, Decimal("350.00"))
    
    assert result_token is None
    assert fsm.get_status(oid) == OrderStatus.REJECTED

@pytest.mark.asyncio
async def test_successful_validation_returns_token() -> None:
    """모든 검증 통과 시 RiskApprovalToken 정상 발급 증명"""
    bus = EventBus()
    fsm = OmsFsm()
    manager = RiskManager(bus, fsm, max_qty=100, max_deviation_pct=Decimal("0.10"))
    
    oid = uuid4()
    token = RiskApprovalToken(oid, time.time_ns(), "mock_sig")
    await fsm.register_order(token)
    
    # 모든 조건 정상
    req = OrderRequest(uuid4(), oid, "CODE", Decimal("350.00"), 10, "BUY")
    result_token = await manager.validate_order(req, Decimal("350.00"))
    
    assert result_token is not None
    assert result_token.order_id == oid

def test_decimal_quantization_round_down() -> None:
    """[목표 C 검증] 십진수 연산 시 증권사 거절을 막기 위한 강제 ROUND_DOWN 절사 로직 증명"""
    bus = EventBus()
    fsm = OmsFsm()
    manager = RiskManager(bus, fsm, max_qty=100, max_deviation_pct=Decimal("0.10"))
    
    # 350.555 -> 350.55 로 내림(버림) 처리되어야 함
    result = manager._quantize_down(Decimal("350.559"))
    assert result == Decimal("350.55")
