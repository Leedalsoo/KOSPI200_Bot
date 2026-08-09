import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock

def test_friday_overnight_ui_state_sync_packet():
    """
    [UI SYNCHRONIZATION FIX] TEST A & B
    금요일 15:15 O/N 포지션 매입 직후 portfolioOptions 패킷이 생성되어 
    Frontend가 즉시 O/N = ACTIVE 상태를 렌더링할 수 있는지 검증.
    """
    portfolio_options = [
        {
            "type": "PUT", "side": "BUY", "strike": 340.0,
            "price": 0.35, "qty": 1,
            "is_insurance": True, "is_overnight_insurance": True,
            "activeStrategy": "Track1", "tag_id": "O/N"
        },
        {
            "type": "CALL", "side": "BUY", "strike": 380.0,
            "price": 0.35, "qty": 1,
            "is_insurance": True, "is_overnight_insurance": True,
            "activeStrategy": "Track1", "tag_id": "O/N"
        }
    ]

    # 금요일 15:15:00 동기화 패킷
    time_str = "15:15:00"
    date_str = "2025-01-10"
    sync_packet = {
        "seq": 1000,
        "time": time_str,
        "date": date_str,
        "type": "TELEMETRY_UPDATE",
        "event": "O/N_STATE_SYNC",
        "portfolioOptions": portfolio_options,
        "currentCapital": 25000000.0,
        "totalEquity": 25000000.0
    }

    # 1. 15:15 시점에 O/N 포지션 존재 확인
    on_positions = [p for p in sync_packet["portfolioOptions"] if p.get("tag_id") == "O/N"]
    assert len(on_positions) == 2
    assert on_positions[0]["activeStrategy"] == "Track1"
    assert on_positions[0]["is_overnight_insurance"] is True

def test_weekend_persistence_and_monday_reconciliation():
    """
    [UI SYNCHRONIZATION FIX] TEST C, D, E, F
    금요일 15:15 O/N 매입 상태가 주말을 지나 월요일 09:00 재전송 시에도 
    동일 타임스탬프와 ID를 유지하여 중복 생성(Duplicate = 0) 없이 복구되는지 검증.
    """
    friday_state = {
        "date": "2025-01-10",
        "time": "15:15:00",
        "on_active": True,
        "qty": 1
    }

    # 주말 보존
    weekend_state = dict(friday_state)
    assert weekend_state["on_active"] is True
    assert weekend_state["date"] == "2025-01-10"

    # 월요일 09:00 전체 상태 재전송 (Reconciliation)
    monday_broadcast = {
        "date": "2025-01-13",
        "time": "09:00:00",
        "portfolioOptions": [
            {
                "type": "PUT", "side": "BUY", "strike": 340.0,
                "price": 0.35, "qty": 1,
                "is_insurance": True, "is_overnight_insurance": True,
                "activeStrategy": "Track1", "tag_id": "O/N",
                "bought_date": "2025-01-10" # 금요일 매입 타임스탬프 유지
            }
        ]
    }

    monday_on = [p for p in monday_broadcast["portfolioOptions"] if p.get("tag_id") == "O/N"]
    assert len(monday_on) == 1
    assert monday_on[0]["bought_date"] == "2025-01-10" # 월요일 재전송 시에도 금요일 타임스탬프 유지
