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
    경과시간(초) 기반 타임아웃 헬퍼 (Wall Clock 및 Virtual Simulation Time 겸용)
    """
    def __init__(self, timeout_seconds: float, current_sim_time: Optional[float] = None) -> None:
        self.timeout_seconds: float = timeout_seconds
        self.start_time: float = current_sim_time if current_sim_time is not None else time.time()

    def reset(self, current_sim_time: Optional[float] = None) -> None:
        """타이머 리셋"""
        self.start_time = current_sim_time if current_sim_time is not None else time.time()

    def elapsed(self, current_sim_time: Optional[float] = None) -> float:
        """경과 시간(초) 반환"""
        now = current_sim_time if current_sim_time is not None else time.time()
        return now - self.start_time

    def is_expired(self, current_sim_time: Optional[float] = None) -> bool:
        """타임아웃 여부 반환"""
        return self.elapsed(current_sim_time) >= self.timeout_seconds


class DynamicProfitRebuildEvaluator:
    """
    [Strategy Optimization] Dynamic Profit-Take & Rebuild 공통 평가기
    
    핵심 역할:
    1. Gross Profit 및 예상 수수료/슬리피지(Exit + Re-entry)를 감안한 Expected Net PnL 계산
    2. Profit Take 조건 판정 (Net PnL >= Threshold)
    3. 중심가격/변동성 기반 가두리 Rebuild Strike 계산 (가두리 확장 및 이동)
    4. 중복 호출 방지 (Idempotency)
    """
    def __init__(self) -> None:
        self.last_profit_take_tick_id: Optional[str] = None

    @staticmethod
    def calculate_expected_net_pnl(
        unrealized_pnl: float,
        qty: int,
        multiplier: float = 250000.0,
        estimated_fee_rate: float = 0.0005,
        estimated_slippage_ticks: int = 1,
        tick_value: float = 12500.0
    ) -> float:
        """
        Exit 및 Re-entry 마찰비용(Fee + Slippage)을 반영한 순예상 손익(Net Expected PnL) 산출
        """
        # Exit + Re-entry 2회 거래 마찰비용 산출
        roundtrip_count = 2
        total_slippage_cost = roundtrip_count * qty * estimated_slippage_ticks * tick_value
        estimated_notional = qty * multiplier
        total_fee_cost = roundtrip_count * estimated_notional * estimated_fee_rate
        
        total_friction_cost = total_slippage_cost + total_fee_cost
        return unrealized_pnl - total_friction_cost

    def evaluate_profit_take(
        self,
        unrealized_pnl: float,
        qty: int,
        profit_target: float,
        tick_id: Optional[str] = None,
        multiplier: float = 250000.0
    ) -> Tuple[bool, float]:
        """
        Net PnL 기준 Profit Take 여부 판정 및 Idempotency 체크
        
        Returns:
            (profit_take_triggered, expected_net_pnl)
        """
        if tick_id is not None and self.last_profit_take_tick_id == tick_id:
            logger.debug("[DynamicProfitRebuildEvaluator] Idempotency Guard: 동일 Tick 중복 판정 방지 (%s)", tick_id)
            return False, 0.0

        net_pnl = self.calculate_expected_net_pnl(unrealized_pnl, qty, multiplier=multiplier)
        if net_pnl >= profit_target and profit_target > 0:
            if tick_id is not None:
                self.last_profit_take_tick_id = tick_id
            return True, net_pnl
        return False, net_pnl

    @staticmethod
    def calculate_rebuild_strikes(
        current_price: float,
        offset: float = 7.5,
        vol_expansion_factor: float = 1.0,
        strike_step: float = 2.5
    ) -> Tuple[float, float]:
        """
        현재 시장 중심가격 및 변동성 확장 요소를 반영한 새로운 가두리 Strike (Call/Put) 산출
        """
        effective_offset = offset * vol_expansion_factor
        call_strike = round((current_price + effective_offset) / strike_step) * strike_step
        put_strike = round((current_price - effective_offset) / strike_step) * strike_step
        return call_strike, put_strike

