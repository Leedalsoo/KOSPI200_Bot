# -*- coding: utf-8 -*-
"""Option Expiry and DTE (Days To Expiry) Calculation Module.

Calculates exact KRX trading days remaining until option expiration date.
"""
from datetime import date, datetime
from typing import Optional, Union

from shared.calendar.krx_calendar import KrxTradingCalendar, _normalize_date


def calculate_dte(
    current_date: Union[date, datetime, str],
    expiry_date: Union[date, datetime, str],
    calendar: Optional[KrxTradingCalendar] = None,
    use_trading_days: bool = True,
) -> float:
    """현재 날짜와 만기일 사이의 DTE(Days to Expiry, 잔여 만기일수) 계산.

    규칙:
    1. current_date >= expiry_date 인 경우 0.0 반환 (당일 만기 D-0 또는 만기 경과).
    2. use_trading_days=True (기본값):
       - KrxTradingCalendar를 이용해 현재일 이후 만기일까지의 실제 KRX 거래일 수(영업일 DTE)를 반환.
       - 당일을 제외하고 만기일까지 남은 거래일 수 계산 (inclusive=False).
       - 예: 오늘이 월요일이고 만기일이 금요일이며 중간에 휴장일이 없다면 -> 화, 수, 목, 금 4거래일 (4.0일).
    3. use_trading_days=False:
       - 단순 달력일 수 차이 (expiry_date - current_date).days 반환.
    """
    cur_d = _normalize_date(current_date)
    exp_d = _normalize_date(expiry_date)

    if cur_d >= exp_d:
        return 0.0

    if not use_trading_days:
        return float((exp_d - cur_d).days)

    cal = calendar or KrxTradingCalendar()
    # 당일을 제외하고 만기일까지 남은 거래일 수 계산
    trading_days = cal.trading_days_between(cur_d, exp_d, inclusive=False)
    return float(trading_days)
