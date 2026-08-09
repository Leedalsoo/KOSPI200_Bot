# -*- coding: utf-8 -*-
from datetime import datetime, time
from typing import Optional

class TimeService:
    """초고빈도 백테스트 및 LIVE 구동을 위한 결정론적 시간 동기화 에이전트"""
    
    def __init__(self, mode: str = "LIVE") -> None:
        if mode not in ("LIVE", "BACKTEST"):
            raise ValueError("mode must be either 'LIVE' or 'BACKTEST'")
        self.mode: str = mode
        self.MARKET_OPEN: time = time(8, 45, 0)
        self.MARKET_CLOSE: time = time(15, 45, 0)
        self._virtual_time: datetime = datetime.min

    def set_virtual_time(self, tick_time: datetime) -> None:
        """[목표 B, C] 백테스트 모드 시 가상 시간 동기화 및 단조 증가 무결성 검증"""
        if self.mode == "LIVE":
            raise RuntimeError("Cannot set virtual time in LIVE mode")
            
        if tick_time < self._virtual_time:
            raise ValueError("Time cannot go backwards")
            
        self._virtual_time = tick_time

    def get_current_time(self) -> datetime:
        """[목표 B] 모드에 따른 현재 시각 반환 (LIVE: 시스템 시각, BACKTEST: 가상 시각)"""
        if self.mode == "LIVE":
            return datetime.now()
        return self._virtual_time

    def is_market_open(self, target: Optional[datetime] = None) -> bool:
        """[목표 A] KOSPI 파생 시장 운영 시간 및 주말 거래 차단 필터"""
        # target이 None이면 get_current_time() 결과를 사용하라.
        t = target if target is not None else self.get_current_time()
        
        # 주말(토=5, 일=6) 필터
        if t.weekday() >= 5:
            return False
            
        # 시간 필터
        current_t = t.time()
        if current_t < self.MARKET_OPEN or current_t >= self.MARKET_CLOSE:
            return False
            
        return True

    def get_time_str(self) -> str:
        """HH:MM:SS 포맷의 현재 시각 문자열 반환 (읽기 전용 샌드박스)"""
        return self.get_current_time().strftime("%H:%M:%S")

    def get_timestamp_ns(self) -> int:
        """나노초 타임스탬프 반환 (Single Source of Truth)"""
        return int(self.get_current_time().timestamp() * 1_000_000_000)

