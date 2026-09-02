# -*- coding: utf-8 -*-
"""KRX Trading Calendar Domain Interface and Engine.

Provides minimal, deterministic trading day evaluation, week-start detection,
and trading day counting for the KOSPI200 derivatives trading infrastructure.
"""
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta
from typing import Optional, Set, Union


def _normalize_date(d: Union[date, datetime, str]) -> date:
    """날짜 입력을 datetime.date 객체로 정규화."""
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    if isinstance(d, str):
        # "YYYY-MM-DD" 또는 "YYYY-MM-DD HH:MM:SS" 또는 ISO 포맷 지원
        cleaned = d.strip()
        if " " in cleaned:
            cleaned = cleaned.split(" ")[0]
        elif "T" in cleaned:
            cleaned = cleaned.split("T")[0]
        return datetime.strptime(cleaned, "%Y-%m-%d").date()
    raise TypeError(f"Unsupported date type: {type(d)}")


class IHolidayDataProvider(ABC):
    """KRX 공휴일/휴장일 데이터 공급원 인터페이스 (추상 계약)."""

    @abstractmethod
    def is_holiday(self, target_date: date) -> bool:
        """주어진 날짜가 공식 공휴일/휴장일인지 여부 반환."""
        raise NotImplementedError

    @abstractmethod
    def get_holidays_for_year(self, year: int) -> Set[date]:
        """특정 연도의 공식 공휴일/휴장일 집합 반환."""
        raise NotImplementedError


class InMemoryHolidayProvider(IHolidayDataProvider):
    """메모리 기반 공휴일 데이터 공급원 (주입식/테스트용/외부데이터 연동용)."""

    def __init__(self, holidays: Optional[Set[date]] = None) -> None:
        self._holidays: Set[date] = set(holidays or [])

    def add_holiday(self, holiday: Union[date, datetime, str]) -> None:
        """휴장일 등록."""
        self._holidays.add(_normalize_date(holiday))

    def add_holidays(self, holidays: Set[Union[date, datetime, str]]) -> None:
        """복수 휴장일 등록."""
        for h in holidays:
            self.add_holiday(h)

    def is_holiday(self, target_date: date) -> bool:
        return target_date in self._holidays

    def get_holidays_for_year(self, year: int) -> Set[date]:
        return {h for h in self._holidays if h.year == year}


class KrxTradingCalendar:
    """KRX 거래일 판정 및 주간 개장일/DTE 기반 캘린더 엔진.
    
    원칙:
    1. 주말(토, 일)은 기본 비거래일.
    2. 공휴일/휴장일 판정은 주입된 IHolidayDataProvider에 완전히 위임하여 임의 하드코딩을 배제.
    3. 주간 첫 거래일은 해당 주(월~금)에서 공휴일을 제외한 최초 거래일로 결정론적 판정.
    """

    def __init__(self, holiday_provider: Optional[IHolidayDataProvider] = None) -> None:
        self.holiday_provider: IHolidayDataProvider = holiday_provider or InMemoryHolidayProvider()

    def is_trading_day(self, target: Union[date, datetime, str]) -> bool:
        """주어진 날짜가 KRX 정규 거래일인지 판정.
        
        조건:
        - 토요일(5), 일요일(6) 제외
        - Holiday Provider에 등록된 공휴일/휴장일 제외
        """
        d = _normalize_date(target)
        # 주말(토=5, 일=6) 필터
        if d.weekday() >= 5:
            return False
        # 공휴일 필터
        if self.holiday_provider.is_holiday(d):
            return False
        return True

    def next_trading_day(self, target: Union[date, datetime, str], offset: int = 1) -> date:
        """주어진 날짜 이후 offset번째 거래일 반환."""
        if offset < 1:
            raise ValueError("offset must be >= 1")
        cur = _normalize_date(target)
        count = 0
        while count < offset:
            cur += timedelta(days=1)
            if self.is_trading_day(cur):
                count += 1
        return cur

    def prev_trading_day(self, target: Union[date, datetime, str], offset: int = 1) -> date:
        """주어진 날짜 이전 offset번째 거래일 반환."""
        if offset < 1:
            raise ValueError("offset must be >= 1")
        cur = _normalize_date(target)
        count = 0
        while count < offset:
            cur -= timedelta(days=1)
            if self.is_trading_day(cur):
                count += 1
        return cur

    def trading_days_between(
        self,
        start_date: Union[date, datetime, str],
        end_date: Union[date, datetime, str],
        inclusive: bool = True,
    ) -> int:
        """두 날짜 사이의 실제 거래일 수 계산 (DTE 산출 기초).
        
        start_date > end_date 인 경우 0 반환.
        """
        start_d = _normalize_date(start_date)
        end_d = _normalize_date(end_date)
        if start_d > end_d:
            return 0

        count = 0
        cur = start_d
        while cur <= end_d:
            if self.is_trading_day(cur):
                if cur == start_d and not inclusive:
                    pass
                else:
                    count += 1
            cur += timedelta(days=1)
        return count

    def is_week_start_trading_day(self, target: Union[date, datetime, str]) -> bool:
        """주어진 날짜가 해당 주(Week)의 첫 번째 정규 거래일인지 판정.
        
        판정 로직:
        - 대상 날짜가 거래일이 아니면 False.
        - 대상 날짜가 속한 주의 월요일부터 시작하여 최초로 나타나는 거래일과 일치하면 True.
        - 예: 월요일이 공휴일인 주간은 화요일이 True, 월요일이 거래일인 주간은 월요일만 True.
        """
        d = _normalize_date(target)
        if not self.is_trading_day(d):
            return False

        # 해당 주의 월요일 (weekday 0)
        monday = d - timedelta(days=d.weekday())
        first_trading_day: Optional[date] = None

        # 월(0)부터 금(4)까지 순회하며 첫 거래일 탐색
        for offset in range(5):
            candidate = monday + timedelta(days=offset)
            if self.is_trading_day(candidate):
                first_trading_day = candidate
                break

        return first_trading_day == d

    def is_new_week_start(self, target: Union[date, datetime, str]) -> bool:
        """is_week_start_trading_day의 간결한 별칭 (Track 7 연계용)."""
        return self.is_week_start_trading_day(target)
