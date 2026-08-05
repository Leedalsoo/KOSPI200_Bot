# -*- coding: utf-8 -*-
"""
strategy/common.py

[Phase 0] 공통 베이스 유틸리티 모듈

핵심 역할:
1. TradingDateResetHelper: 영업일/세션 경계 자동 감지 및 원자적 상태 리셋
2. ExecutionCostCalculator: 실시간 호가/체결가 기반 슬리피지 및 손익 계산
3. AtomicBudgetManager: 트랙 간 공유 예산(insurance_budget_pool)의 동시성 안전 원자적 체크-앤-차감
4. TimeUtils: datetime.time 기반 파싱 및 장운영 시각(15:15등) 판단
5. WallClockTimer: wall-clock 경과시간(초) 기반 타임아웃 판단
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, date, time as dtime
from decimal import Decimal
from typing import Dict, Optional, Tuple, Any

logger = logging.getLogger(__name__)


class TradingDateResetHelper:
    """
    영업일/세션 경계 리셋 헬퍼
    last_trading_date를 관리하여 날짜 변경 시 플래그 리셋 여부를 판정합니다.
    """
    def __init__(self, initial_date: Optional[str | date] = None) -> None:
        self.last_trading_date: Optional[str] = self._normalize_date(initial_date)

    @staticmethod
    def _normalize_date(d: Optional[str | date]) -> Optional[str]:
        if d is None:
            return None
        if isinstance(d, date):
            return d.strftime("%Y-%m-%d")
        return d

    def check_and_update(self, current_date: str | date) -> bool:
        """
        현재 날짜가 이전 날짜와 다르면 last_trading_date를 갱신하고 True(리셋 필요) 반환.
        단, UNKNOWN 또는 무효 날짜는 무시하여 무한 핑퐁 리셋 방지.
        """
        curr_str = self._normalize_date(current_date)
        if not curr_str or curr_str.upper() == "UNKNOWN":
            return False

        if self.last_trading_date is None:
            self.last_trading_date = curr_str
            return True

        if self.last_trading_date != curr_str:
            logger.info(
                "[TradingDateResetHelper] 영업일 변경 감지: %s -> %s (상태 리셋 수행)",
                self.last_trading_date,
                curr_str,
            )
            self.last_trading_date = curr_str
            return True
        return False


class ExecutionCostCalculator:
    """
    실체결가 및 호가(Bid/Ask) 기반 슬리피지 및 평가 손익/비용 계산 유틸
    """
    @staticmethod
    def calc_execution_price(
        side: str,
        bid: Decimal | float,
        ask: Decimal | float,
        slippage_ticks: int = 0,
        tick_size: Decimal | float = 0.05,
    ) -> Decimal:
        """
        주문 방향(BUY/SELL) 및 슬리피지 틱에 따른 실제 가상 체결가 계산
        """
        dec_bid = Decimal(str(bid))
        dec_ask = Decimal(str(ask))
        dec_tick = Decimal(str(tick_size))
        side_upper = side.upper()

        if side_upper == "BUY":
            # 매수 시 Ask에 슬리피지 가산
            base_price = dec_ask if dec_ask > Decimal("0") else dec_bid
            return base_price + (dec_tick * Decimal(slippage_ticks))
        else:
            # 매도 시 Bid에 슬리피지 차감
            base_price = dec_bid if dec_bid > Decimal("0") else dec_ask
            return max(Decimal("0.01"), base_price - (dec_tick * Decimal(slippage_ticks)))

    @staticmethod
    def calc_realized_pnl(
        side: str,
        entry_price: Decimal | float,
        exit_price: Decimal | float,
        qty: int,
        multiplier: float = 250000.0,
    ) -> float:
        """
        실시간 체결가 기반 정확한 청산 손익 산출
        """
        dec_entry = Decimal(str(entry_price))
        dec_exit = Decimal(str(exit_price))
        dec_qty = Decimal(qty)
        dec_mult = Decimal(str(multiplier))

        if side.upper() == "BUY":
            pnl_dec = (dec_exit - dec_entry) * dec_qty * dec_mult
        else:
            pnl_dec = (dec_entry - dec_exit) * dec_qty * dec_mult

        return float(pnl_dec)


class AtomicBudgetManager:
    """
    트랙 간 공유 예산(insurance_budget_pool)의 동시성 안전 원자적 체크-앤-차감 매니저
    """
    def __init__(self, initial_budget: float = 1000000.0) -> None:
        self._budget: float = initial_budget
        self._lock = asyncio.Lock()

    @property
    def current_budget(self) -> float:
        return self._budget

    def set_budget(self, budget: float) -> None:
        self._budget = budget

    async def try_deduct(self, amount: float) -> Tuple[bool, float]:
        """
        원자적으로 예산 차감을 시도합니다.
        
        Returns:
            (성공여부, 차감 후 남은 예산)
        """
        async with self._lock:
            if amount <= 0:
                return True, self._budget

            if self._budget >= amount:
                self._budget -= amount
                logger.info(
                    "[AtomicBudgetManager] 예산 차감 성공: -₩%s | 잔여 예산: ₩%s",
                    f"{amount:,.0f}",
                    f"{self._budget:,.0f}",
                )
                return True, self._budget
            else:
                logger.warning(
                    "[AtomicBudgetManager] 예산 부족 차감 거부! 요청: ₩%s | 현재 잔액: ₩%s",
                    f"{amount:,.0f}",
                    f"{self._budget:,.0f}",
                )
                return False, self._budget

    def try_deduct_sync(self, amount: float) -> Tuple[bool, float]:
        """
        동기 방식 단순 차감 시도
        """
        if amount <= 0:
            return True, self._budget

        if self._budget >= amount:
            self._budget -= amount
            return True, self._budget
        return False, self._budget


class TimeUtils:
    """
    datetime.time 기반 정확한 시각 비교 유틸
    """
    @staticmethod
    def parse_time(time_input: str | dtime) -> dtime:
        if isinstance(time_input, dtime):
            return time_input
        # "15:15:00" or "15:15"
        parts = time_input.split(":")
        hour = int(parts[0])
        minute = int(parts[1])
        second = int(parts[2]) if len(parts) > 2 else 0
        return dtime(hour, minute, second)

    @classmethod
    def is_after_or_equal(cls, current: str | dtime | datetime, target: str | dtime) -> bool:
        """
        current 시각이 target 시각 이상(같거나 이후)인지 판정
        """
        target_t = cls.parse_time(target)
        if isinstance(current, datetime):
            curr_t = current.time()
        else:
            curr_t = cls.parse_time(current)

        return curr_t >= target_t

    @classmethod
    def is_before_or_equal(cls, current: str | dtime | datetime, target: str | dtime) -> bool:
        """
        current 시각이 target 시각 이하(같거나 이전)인지 판정
        """
        target_t = cls.parse_time(target)
        if isinstance(current, datetime):
            curr_t = current.time()
        else:
            curr_t = cls.parse_time(current)

        return curr_t <= target_t


class WallClockTimer:
    """
    실제 wall-clock 경과시간(초) 기반 타임아웃 헬퍼
    """
    def __init__(self, timeout_seconds: float) -> None:
        self.timeout_seconds: float = timeout_seconds
        self.start_time: float = time.time()

    def reset(self) -> None:
        """타이머 리셋"""
        self.start_time = time.time()

    def elapsed(self) -> float:
        """경과 시간(초) 반환"""
        return time.time() - self.start_time

    def is_expired(self) -> bool:
        """타임아웃 여부 반환"""
        return self.elapsed() >= self.timeout_seconds
