from typing import Tuple
from collections import deque
import random
import time
from datetime import datetime, timedelta, date
import logging

logger = logging.getLogger(__name__)

class CalendarSimulator:
    def __init__(self, start_date_str: str = "2025-01-01"):
        # 역사적 영업일 대신 2025-01-01부터 1일씩 진짜 전진하는 리얼 달력 시뮬레이션
        self.current_date = datetime.strptime(start_date_str, "%Y-%m-%d")
        self.current_time = self.current_date.replace(hour=9, minute=0, second=0)
        
        # 🛡️ 만기 잔여일 정수 관리 (초기 D-20 설정)
        self.remaining_days = 20
        self.simulated_days_to_expiry = float(self.remaining_days)

        # 시작 가상 일시 기록
        self.start_datetime_str = self.current_time.strftime("%Y-%m-%d %H:%M:%S")
        expiry_dt = self.current_time + timedelta(days=self.remaining_days)
        self.expiry_datetime_str = expiry_dt.strftime("%Y-%m-%d 15:45:00")

    def is_korean_holiday(self, d: date) -> bool:
        """토요일, 일요일 및 한국 대표 법정공휴일 판정"""
        if d.weekday() in (5, 6):  # 토(5), 일(6) 주말
            return True
        
        # 2025년 한국 공휴일 (대체공휴일 포함)
        holidays_2025 = {
            (1, 1), (1, 28), (1, 29), (1, 30), (3, 1), (3, 3), (5, 5), (5, 6), (6, 6), 
            (8, 15), (10, 3), (10, 5), (10, 6), (10, 7), (10, 8), (10, 9), (12, 25)
        }
        
        m_d = (d.month, d.day)
        if d.year == 2025:
            return m_d in holidays_2025
        
        # 기본 고정 법정공휴일
        fixed_holidays = {
            (1, 1), (3, 1), (5, 5), (6, 6), (8, 15), (10, 3), (10, 9), (12, 25)
        }
        return m_d in fixed_holidays

    def tick(self, elapsed_real_seconds: float = 0.1) -> Tuple[str, str, bool, bool]:
        # 1초당 300초 전진 비율 (장 중)
        advance_seconds = max(1, int(elapsed_real_seconds * 300.0))
        self.current_time += timedelta(seconds=advance_seconds)

        # 주말 및 공휴일인 경우 즉시 다음 영업일 개장 시각(09:00)으로 워프 처리하여 무한 멈춤 방어
        date_changed = False
        while self.is_korean_holiday(self.current_time.date()):
            self.current_date += timedelta(days=1)
            self.current_time = self.current_date.replace(hour=9, minute=0, second=0)
            date_changed = True

        sec = self.current_time.second
        if sec < 15:
            self.current_time = self.current_time.replace(second=0)
        elif sec < 45:
            self.current_time = self.current_time.replace(second=30)
        else:
            try:
                self.current_time = self.current_time.replace(second=0) + timedelta(minutes=1)
            except ValueError:
                self.current_time = self.current_time.replace(second=0)

        is_holiday = self.is_korean_holiday(self.current_time.date())
        is_market_open = not is_holiday and (
            (self.current_time.hour == 9 and self.current_time.minute >= 0) or
            (9 < self.current_time.hour < 15) or
            (self.current_time.hour == 15 and self.current_time.minute <= 45)
        )
        
        if not is_market_open and not is_holiday:
            if self.current_time.hour >= 15 and self.current_time.minute > 45:
                # 익영업일로 워프
                self.current_time += timedelta(days=1)
                self.current_time = self.current_time.replace(hour=9, minute=0, second=0)
                date_changed = True
                while self.is_korean_holiday(self.current_time.date()):
                    self.current_time += timedelta(days=1)
                self.current_date = self.current_time

        if date_changed:
            if self.remaining_days > 0:
                self.remaining_days -= 1
            if self.remaining_days <= 0:
                self.remaining_days = 20 # 롤오버
                
        # 15:45 도달 비율로 당일 차감 계산 (선형 보간)
        start_of_day = self.current_time.replace(hour=9, minute=0, second=0)
        elapsed_sec = (self.current_time - start_of_day).total_seconds()
        fraction_of_day = min(1.0, max(0.0, elapsed_sec / 24300.0))
        self.simulated_days_to_expiry = max(0.001, float(self.remaining_days) - fraction_of_day)

        date_str = self.current_time.strftime("%Y-%m-%d")
        time_str = self.current_time.strftime("%H:%M:%S")
        
        return date_str, time_str, is_market_open, date_changed


class VirtualMarketFeed:
    """
    MarketDataSource 계층 (시뮬레이션 전용)
    과거 mock_ws_server.py의 CalendarSimulator 및 8대 붕괴 시나리오 난수 발생기를 탑재함.
    """
    def __init__(self, initial_price=350.0):
        self.price_history = deque(maxlen=60)
        self.current_price = initial_price
        self.last_tick_time = time.time()
        self.calendar = CalendarSimulator("2025-01-01")
        
        # 스트레스 시나리오 상태 플래그
        self.circuit_breaker_active = False
        self.flash_crash_active = False
        self.iv_explosion_active = False
        self.liquidity_drought_active = False
        
        # 내부 카운터
        self.circuit_breaker_countdown = 0
        self.flash_crash_countdown = 0
        self.liquidity_drought_countdown = 0
        self.iv_explosion_countdown = 0
        
    def next_tick(self) -> Tuple[float, str, bool]:
        now = time.time()
        elapsed = now - self.last_tick_time
        self.last_tick_time = now
        
        # 1. 캘린더 전진
        date_str, time_str, is_market_open, date_changed = self.calendar.tick(elapsed)
        self.sim_date = self.calendar.current_time # 외부 접근용 포인터
        self.days_to_expiry = self.calendar.simulated_days_to_expiry
        
        # 오버나이트 갭 (날짜 변경 시)
        if date_changed:
            if random.random() < 0.3:
                gap_pct = random.uniform(0.008, 0.015)
                gap_dir = random.choice([-1, 1])
                self.current_price = round(self.current_price * (1.0 + gap_dir * gap_pct), 2)
                logger.info(f"⚡ [OVERNIGHT GAP] 개장 갭 발생: {self.current_price}pt")
                
        # 2. 8대 스트레스 시나리오 모사 엔진
        is_halted = False
        regime = "NORMAL"
        step = random.gauss(0, 0.15)
        
        # - 서킷 브레이커 감지
        if self.circuit_breaker_countdown > 0:
            self.circuit_breaker_countdown -= 1
            is_halted = True
            logger.warning(f"🚨 [CIRCUIT BREAKER] 시장 정지 중... ({self.circuit_breaker_countdown}틱 남음)")
            return self.current_price, "CIRCUIT_BREAKER", is_halted
            
        # - 플래시 크래시
        if self.flash_crash_countdown > 0:
            self.flash_crash_countdown -= 1
            step = random.gauss(-1.5, 0.5) # 하방 압력 폭발
            regime = "CRASH"
        elif random.random() < 0.005:
            self.flash_crash_active = True
            self.flash_crash_countdown = random.randint(15, 30)
            logger.critical("🚨 [FLASH CRASH TRIGGERED] 순간 급락 발생!")
        else:
            self.flash_crash_active = False
            
        # - 유동성 고갈
        if self.liquidity_drought_countdown > 0:
            self.liquidity_drought_countdown -= 1
            step = random.gauss(0, 2.0) # 가격이 이리저리 심하게 튀는 호가 공백
            regime = "DROUGHT"
        elif random.random() < 0.003:
            self.liquidity_drought_active = True
            self.liquidity_drought_countdown = random.randint(20, 40)
            logger.critical("🚨 [LIQUIDITY DROUGHT] 호가 공백 발생!")
        else:
            self.liquidity_drought_active = False
            
        # - IV 폭발 (변동성)
        if self.iv_explosion_countdown > 0:
            self.iv_explosion_countdown -= 1
            regime = "IV_EXPLOSION"
        elif random.random() < 0.004:
            self.iv_explosion_active = True
            self.iv_explosion_countdown = random.randint(10, 20)
            logger.critical("🚨 [IV EXPLOSION] 내재변동성 폭발!")
        else:
            self.iv_explosion_active = False
            
        if not self.flash_crash_active and not self.liquidity_drought_active:
            if step > 1.0 or step < -1.0:
                regime = "HIGH_VOLATILITY"

        # 서킷 브레이커 발생 조건 (하방 -8% 등, 여기서는 모의 확률로 발생)
        if random.random() < 0.001:
            self.circuit_breaker_active = True
            self.circuit_breaker_countdown = random.randint(30, 50)
            logger.critical("🚨 [CIRCUIT BREAKER TRIGGERED] 거래가 일시 정지됩니다!")
        else:
            self.circuit_breaker_active = False

        self.current_price = round(self.current_price + step, 2)
        self.current_price = max(100.0, self.current_price) # 하한 락
        
        self.price_history.append(self.current_price)
        
        return self.current_price, regime, is_halted
