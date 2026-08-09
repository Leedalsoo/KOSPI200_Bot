# -*- coding: utf-8 -*-
import pytest
import asyncio
from datetime import datetime, date, time as dtime
from decimal import Decimal

from strategy.common import (
    TradingDateResetHelper,
    ExecutionCostCalculator,
    AtomicBudgetManager,
    TimeUtils,
    WallClockTimer,
)


def test_trading_date_reset_helper():
    helper = TradingDateResetHelper("2025-01-10")
    
    # 동일한 날짜 확인 -> 리셋 불요 (False)
    assert helper.check_and_update("2025-01-10") is False
    assert helper.last_trading_date == "2025-01-10"

    # UNKNOWN 또는 None 수신 시 무시 (False)
    assert helper.check_and_update("UNKNOWN") is False
    assert helper.check_and_update(None) is False
    assert helper.last_trading_date == "2025-01-10"

    # 날짜 변경 감지 -> 리셋 필요 (True)
    assert helper.check_and_update("2025-01-13") is True
    assert helper.last_trading_date == "2025-01-13"

    # date 객체 전달 테스트
    assert helper.check_and_update(date(2025, 1, 13)) is False
    assert helper.check_and_update(date(2025, 1, 14)) is True
    assert helper.last_trading_date == "2025-01-14"

    # 초기 날짜가 None 또는 UNKNOWN일 때 최초 정상 날짜 수신 -> 초기 등록 후 True 반환
    empty_helper = TradingDateResetHelper(None)
    assert empty_helper.check_and_update("UNKNOWN") is False
    assert empty_helper.check_and_update("2025-01-10") is True
    assert empty_helper.last_trading_date == "2025-01-10"


def test_execution_cost_calculator():
    # BUY 시 Ask 가격 + 슬리피지
    buy_price = ExecutionCostCalculator.calc_execution_price("BUY", bid=2.00, ask=2.05, slippage_ticks=1, tick_size=0.05)
    assert buy_price == Decimal("2.10")

    # SELL 시 Bid 가격 - 슬리피지
    sell_price = ExecutionCostCalculator.calc_execution_price("SELL", bid=2.00, ask=2.05, slippage_ticks=1, tick_size=0.05)
    assert sell_price == Decimal("1.95")

    # PnL 산출 검증 (BUY 1계약 2.0 -> 3.0 이익: +250,000)
    buy_pnl = ExecutionCostCalculator.calc_realized_pnl("BUY", entry_price=2.0, exit_price=3.0, qty=1, multiplier=250000.0)
    assert buy_pnl == 250000.0

    # PnL 산출 검증 (SELL 1계약 3.0 -> 2.0 이익: +250,000)
    sell_pnl = ExecutionCostCalculator.calc_realized_pnl("SELL", entry_price=3.0, exit_price=2.0, qty=1, multiplier=250000.0)
    assert sell_pnl == 250000.0


@pytest.mark.asyncio
async def test_atomic_budget_manager():
    bm = AtomicBudgetManager(initial_budget=1000000.0)
    assert bm.current_budget == 1000000.0

    # 1. 300,000 차감 성공
    success, rem = await bm.try_deduct(300000.0)
    assert success is True
    assert rem == 700000.0
    assert bm.current_budget == 700000.0

    # 2. 800,000 차감 시도 -> 잔액 부족 거부
    success, rem = await bm.try_deduct(800000.0)
    assert success is False
    assert rem == 700000.0

    # 3. 동기 방식 차감
    success_sync, rem_sync = bm.try_deduct_sync(200000.0)
    assert success_sync is True
    assert rem_sync == 500000.0


def test_time_utils():
    # 1. 시각 파싱
    t1 = TimeUtils.parse_time("15:15:00")
    assert t1 == dtime(15, 15, 0)

    # 2. is_after_or_equal
    dt_now = datetime(2025, 1, 10, 15, 20, 0)
    assert TimeUtils.is_after_or_equal(dt_now, "15:15:00") is True
    assert TimeUtils.is_after_or_equal(dtime(15, 10, 0), "15:15:00") is False

    # 3. is_before_or_equal
    assert TimeUtils.is_before_or_equal(dtime(15, 10, 0), "15:15:00") is True
    assert TimeUtils.is_before_or_equal(dtime(15, 20, 0), "15:15:00") is False


def test_wall_clock_timer():
    timer = WallClockTimer(timeout_seconds=0.1)
    assert timer.is_expired() is False

    # 0.12초 대기
    import time
    time.sleep(0.12)
    assert timer.is_expired() is True

    # 리셋 후 정상 초기화 확인
    timer.reset()
    assert timer.is_expired() is False
