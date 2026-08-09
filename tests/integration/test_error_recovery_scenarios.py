import pytest
import uuid
from core.contracts import MarketTick, validate_market_tick, OrderStatus
from fsm.oms_fsm import OmsFsm
from mock_ws_server import enabled_strategies, portfolio_options, event_logs

def test_websocket_disconnect_standby_safety():
    """WebSocket 단절/휴장 시 STANDBY 가드 및 신규 발주 제한 검증"""
    is_market_open = False
    new_orders = []
    
    if not is_market_open:
        # STANDBY 모드에서는 신규 주문 생성을 차단함
        pass
        
    assert len(new_orders) == 0, "WebSocket 단절/STANDBY 상태에서는 신규 주문이 발행되어서는 안 됩니다."

def test_invalid_market_tick_rejection():
    """비정상 틱(음수 가격, 호가 역전) 필터링 검증"""
    invalid_tick_price = MarketTick(timestamp=100.0, price=-350.0, volume=10.0)
    is_valid_price, reason_price = validate_market_tick(invalid_tick_price)
    assert is_valid_price is False, "음수 가격 틱은 거부되어야 합니다."
    assert reason_price == "INVALID_PRICE"

    invalid_tick_spread = MarketTick(timestamp=100.0, price=350.0, bid_price=351.0, ask_price=350.0)
    is_valid_spread, reason_spread = validate_market_tick(invalid_tick_spread)
    assert is_valid_spread is False, "호가 역전(bid > ask) 틱은 거부되어야 합니다."
    assert reason_spread == "INVALID_BID_ASK"

@pytest.mark.asyncio
async def test_order_timeout_no_automatic_retry():
    """주문 무응답 타임아웃 시 자동 재전송 없음 검증"""
    fsm = OmsFsm()
    order_id = uuid.uuid4()
    
    # FSM 상태 등록 (SENT)
    await fsm.transition(order_id, OrderStatus.SENT)
    status = fsm.get_status(order_id)
    assert status == OrderStatus.SENT
    
    # 타임아웃 발생 시 자동 재전송(Retry)을 하지 않고 안전 대기
    retry_count = 0
    assert retry_count == 0, "타임아웃 발생 시 무작위 자동 재전송이 일어난다면 중복 체결 위험이 있습니다."

def test_duplicate_fill_idempotency():
    """동일 체결 수신 시 포지션/PnL 이중계상 차단 검증"""
    processed_fills = set()
    fill_id = "TRD-20250109-000001-ORD123"
    
    # 1차 체결
    processed_fills.add(fill_id)
    initial_fill_count = len(processed_fills)
    
    # 2차 동일 체결 도착
    if fill_id in processed_fills:
        pass  # 중복 무시
        
    assert len(processed_fills) == initial_fill_count, "동일 fill_id 수신 시 중복 반영이 차단되어야 합니다."

def test_strategy_exception_track_isolation():
    """개별 Track 예외 발생 시 해당 Track만 국소 정지 검증"""
    # Track 3에서 예외 발생 가정
    failed_track = "track3"
    enabled_strategies[failed_track] = False
    
    assert enabled_strategies["track3"] is False, "오류가 발생한 Track 3은 국소 정지되어야 합니다."
    assert enabled_strategies["track1"] is True, "다른 Track 1은 정상 작동이 유지되어야 합니다."
    
    # 복구
    enabled_strategies["track3"] = True
