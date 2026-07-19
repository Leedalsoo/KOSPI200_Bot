import pytest
from datetime import datetime
from infra.time_service import TimeService

def test_kospi_derivative_active_hours() -> None:
    """[목표 A 검증] KOSPI 파생 조기 개장/장마감 및 주말 필터 증명"""
    service = TimeService()
    
    valid_time = datetime(2026, 7, 13, 8, 45, 0)  # 월요일 08:45:00
    invalid_early = datetime(2026, 7, 13, 8, 44, 59)
    invalid_late = datetime(2026, 7, 13, 15, 45, 1)
    weekend = datetime(2026, 7, 18, 10, 0, 0)  # 토요일

    assert service.is_market_open(valid_time) is True
    assert service.is_market_open(invalid_early) is False
    assert service.is_market_open(invalid_late) is False
    assert service.is_market_open(weekend) is False

def test_virtual_time_monotonic_defense() -> None:
    """[목표 B, C 검증] BACKTEST 모드에서 시간 역행(Time Travel) 차단 증명"""
    service = TimeService(mode="BACKTEST")
    
    t1 = datetime(2026, 7, 13, 10, 0, 0)
    t2 = datetime(2026, 7, 13, 10, 0, 1)
    t_past = datetime(2026, 7, 13, 9, 59, 59)
    
    service.set_virtual_time(t1)
    assert service.get_current_time() == t1
    
    service.set_virtual_time(t2)
    assert service.get_current_time() == t2
    
    with pytest.raises(ValueError, match="Time cannot go backwards"):
        service.set_virtual_time(t_past)

def test_live_mode_ignores_virtual_time() -> None:
    """[목표 B 검증] LIVE 모드에서 set_virtual_time 동작 무시 또는 차단 증명"""
    service = TimeService(mode="LIVE")
    t1 = datetime(2026, 7, 13, 10, 0, 0)
    
    # LIVE 모드에서는 virtual_time을 세팅해도 get_current_time()이 시스템 시각을 반환하거나, 세팅 자체가 에러를 뿜어야 한다.
    with pytest.raises(RuntimeError):
        service.set_virtual_time(t1)
