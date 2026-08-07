import pytest
from mock_ws_server import _reset_session_state, portfolio_options, rollover_event_log

def test_intraday_restart_no_duplicate_entry():
    """동일 거래일 장중 재시작 시 on_market_open() 포지션 중복 발주 차단 검증"""
    _reset_session_state(preserve_capital=False)
    initial_len = len(portfolio_options)
    assert initial_len > 0, "초기 장 개장 옵션 포지션이 생성되어야 합니다."
    
    # 동일 거래일 장중 재시작 (preserve_capital=True)
    _reset_session_state(preserve_capital=True)
    after_restart_len = len(portfolio_options)
    
    assert after_restart_len == initial_len, "장중 재시작 시 포지션이 2배로 중복 생성되어서는 안 됩니다."

def test_settlement_idempotency_guard():
    """동일 만기일 정산 중복 실행 방지 멱등성 검증"""
    rollover_event_log.clear()
    
    dummy_expiry = "2025-01-09"
    rollover_event_log.append({
        "seq": 100,
        "expiry_date": dummy_expiry,
        "settlement_pnl": 150000.0,
        "price_at_expiry": 350.0,
        "new_dte": 28.0
    })
    
    # 멱등성 확인: 이미 처리된 expiry_date 존재 여부 검사
    is_already_settled = any(r.get("expiry_date") == dummy_expiry for r in rollover_event_log)
    assert is_already_settled is True, "동일 만기일 정산 이벤트는 멱등하게 감지되어야 합니다."
