# -*- coding: utf-8 -*-
"""Unit Tests for Minimal KRX Trading Calendar Interface and Engine."""
import unittest
from datetime import date, datetime

from shared.calendar.krx_calendar import (
    IHolidayDataProvider,
    InMemoryHolidayProvider,
    KrxTradingCalendar,
    _normalize_date,
)


class TestKrxTradingCalendar(unittest.TestCase):
    """KRX 거래일 캘린더 핵심 계약 및 인터페이스 검증 스위트."""

    def setUp(self):
        self.holiday_provider = InMemoryHolidayProvider()
        # 2026년 가상 테스트 공휴일 등록
        # 2026-08-24(월)은 정상 거래일
        # 2026-08-31(월)을 대체공휴일로 등록
        self.holiday_provider.add_holiday(date(2026, 8, 31))
        # 2026-09-01(화)도 추가 공휴일로 등록 (연속 휴장 테스트용)
        self.holiday_provider.add_holiday("2026-09-01")

        self.calendar = KrxTradingCalendar(holiday_provider=self.holiday_provider)

    def test_normalize_date(self):
        """다양한 날짜 타입(str, date, datetime) 정규화 검증."""
        expected = date(2026, 8, 24)
        self.assertEqual(_normalize_date(date(2026, 8, 24)), expected)
        self.assertEqual(_normalize_date(datetime(2026, 8, 24, 9, 30, 0)), expected)
        self.assertEqual(_normalize_date("2026-08-24"), expected)
        self.assertEqual(_normalize_date("2026-08-24 09:00:00.000"), expected)
        self.assertEqual(_normalize_date("2026-08-24T09:00:00"), expected)

        with self.assertRaises(TypeError):
            _normalize_date(12345)  # type: ignore

    def test_is_trading_day_weekdays_and_weekends(self):
        """기본 주말(토, 일) 및 평일 거래일 판정 계약 검증."""
        # 2026-08-24 (월) ~ 2026-08-28 (금) -> 모두 거래일
        self.assertTrue(self.calendar.is_trading_day("2026-08-24"))
        self.assertTrue(self.calendar.is_trading_day("2026-08-25"))
        self.assertTrue(self.calendar.is_trading_day("2026-08-26"))
        self.assertTrue(self.calendar.is_trading_day("2026-08-27"))
        self.assertTrue(self.calendar.is_trading_day("2026-08-28"))

        # 2026-08-29 (토), 2026-08-30 (일) -> 주말 비거래일
        self.assertFalse(self.calendar.is_trading_day("2026-08-29"))
        self.assertFalse(self.calendar.is_trading_day("2026-08-30"))

    def test_is_trading_day_with_holidays(self):
        """등록된 공휴일 비거래일 판정 계약 검증."""
        # 2026-08-31 (월, 공휴일 등록됨) -> 비거래일
        self.assertFalse(self.calendar.is_trading_day("2026-08-31"))
        # 2026-09-01 (화, 공휴일 등록됨) -> 비거래일
        self.assertFalse(self.calendar.is_trading_day("2026-09-01"))
        # 2026-09-02 (수, 공휴일 아님) -> 정상 거래일
        self.assertTrue(self.calendar.is_trading_day("2026-09-02"))

    def test_next_and_prev_trading_day_skips_weekends_and_holidays(self):
        """다음/이전 거래일 탐색 시 주말 및 공휴일 건너뛰기 검증."""
        # 2026-08-28 (금) 다음 거래일 -> 8/31(월), 9/1(화)이 공휴일이므로 9/2(수) 반환
        next_day = self.calendar.next_trading_day("2026-08-28")
        self.assertEqual(next_day, date(2026, 9, 2))

        # 2026-09-02 (수) 이전 거래일 -> 2026-08-28 (금) 반환
        prev_day = self.calendar.prev_trading_day("2026-09-02")
        self.assertEqual(prev_day, date(2026, 8, 28))

        # 2번째 이후 거래일 -> 9/2(수)의 2번째 이후 -> 9/4(금)
        next_2nd = self.calendar.next_trading_day("2026-09-02", offset=2)
        self.assertEqual(next_2nd, date(2026, 9, 4))

    def test_trading_days_between_count(self):
        """두 날짜 사이의 순수 거래일 수 계산 (DTE 기반) 검증."""
        # 2026-08-24(월) ~ 2026-08-28(금) -> 5영업일
        count = self.calendar.trading_days_between("2026-08-24", "2026-08-28")
        self.assertEqual(count, 5)

        # 2026-08-28(금) ~ 2026-09-04(금)
        # 포함 날짜: 8/28(금=1), 8/29(토X), 8/30(일X), 8/31(공휴일X), 9/1(공휴일X), 9/2(수=2), 9/3(목=3), 9/4(금=4) -> 총 4영업일
        count_spanning = self.calendar.trading_days_between("2026-08-28", "2026-09-04")
        self.assertEqual(count_spanning, 4)

        # 시작일 > 종료일 -> 0
        self.assertEqual(self.calendar.trading_days_between("2026-09-04", "2026-08-28"), 0)

    def test_is_week_start_trading_day_normal_and_holiday_weeks(self):
        """주간 첫 거래일(is_new_week_start) 판정 계약 검증."""
        # 1. 일반 주간 (2026-08-24 ~ 2026-08-28)
        # 월요일(8/24)만 True, 화~금(8/25~8/28)은 False
        self.assertTrue(self.calendar.is_week_start_trading_day("2026-08-24"))
        self.assertTrue(self.calendar.is_new_week_start("2026-08-24"))
        self.assertFalse(self.calendar.is_week_start_trading_day("2026-08-25"))
        self.assertFalse(self.calendar.is_week_start_trading_day("2026-08-26"))
        self.assertFalse(self.calendar.is_week_start_trading_day("2026-08-27"))
        self.assertFalse(self.calendar.is_week_start_trading_day("2026-08-28"))

        # 2. 월/화요일이 공휴일인 주간 (2026-08-31 월=휴, 2026-09-01 화=휴)
        # 월(8/31) -> False (공휴일)
        # 화(9/01) -> False (공휴일)
        # 수(9/02) -> True (해당 주 최초 개장 거래일)
        # 목(9/03), 금(9/04) -> False
        self.assertFalse(self.calendar.is_week_start_trading_day("2026-08-31"))
        self.assertFalse(self.calendar.is_week_start_trading_day("2026-09-01"))
        self.assertTrue(self.calendar.is_week_start_trading_day("2026-09-02"))
        self.assertTrue(self.calendar.is_new_week_start("2026-09-02"))
        self.assertFalse(self.calendar.is_week_start_trading_day("2026-09-03"))
        self.assertFalse(self.calendar.is_week_start_trading_day("2026-09-04"))

    def test_default_empty_holiday_provider_safety(self):
        """공휴일 데이터가 주입되지 않은 기본 상태에서도 주말 안전 차단 및 오판 방지 검증."""
        bare_cal = KrxTradingCalendar()
        # 월요일 -> True
        self.assertTrue(bare_cal.is_trading_day("2026-08-24"))
        # 토요일 -> False
        self.assertFalse(bare_cal.is_trading_day("2026-08-29"))
        # 일요일 -> False
        self.assertFalse(bare_cal.is_trading_day("2026-08-30"))

    def test_calculate_dte_exact_trading_days(self):
        """DTE 계산 계약: 실제 KRX 거래일 기준 DTE 산출 검증."""
        from shared.calendar.expiry_calculator import calculate_dte

        # 1. 2026-08-24(월) 기준 만기일 2026-08-28(금) -> 4거래일 남음 (화, 수, 목, 금)
        dte = calculate_dte("2026-08-24", "2026-08-28", calendar=self.calendar)
        self.assertEqual(dte, 4.0)

        # 2. 공휴일이 포함된 기간: 2026-08-28(금) 기준 만기일 2026-09-04(금)
        # 8/31(월), 9/1(화) 공휴일 -> 남은 거래일: 9/2(수), 9/3(목), 9/4(금) = 3거래일
        dte_hol = calculate_dte("2026-08-28", "2026-09-04", calendar=self.calendar)
        self.assertEqual(dte_hol, 3.0)

        # 3. 당일 만기 (current == expiry) -> 0.0
        self.assertEqual(calculate_dte("2026-08-28", "2026-08-28", calendar=self.calendar), 0.0)

        # 4. 만기 경과 (current > expiry) -> 0.0
        self.assertEqual(calculate_dte("2026-08-29", "2026-08-28", calendar=self.calendar), 0.0)

        # 5. 달력일 기준 옵션 (use_trading_days=False)
        cal_dte = calculate_dte("2026-08-24", "2026-08-28", use_trading_days=False)
        self.assertEqual(cal_dte, 4.0)

    def test_option_program_runtime_dte_wiring(self):
        """Runtime process_tick에서 CanonicalMarketTick.expiry 기반 DTE 계산 및 Track 1 연동 검증."""
        from shared.contracts.canonical import CanonicalMarketTick
        from option_program.runtime.program_runtime import OptionProgramRuntime

        runtime = OptionProgramRuntime(calendar=self.calendar)

        # 1. Track 1에 가두리 활성화 세팅
        t1 = runtime.strategies[0]
        t1.active_fence = {"type": "CALL", "strike": 355.0, "tag_id": 1}

        # 2. 만기일이 3거래일 남은 틱 주입 (DTE <= 4.0 조건 충족 -> Track 1 FENCE_CLEAR 조기청산 유발)
        # 2026-08-28(금)에 만기일이 2026-09-04(금)인 틱 주입 (중간에 월/화 공휴일로 DTE=3.0)
        tick_d3 = CanonicalMarketTick(
            timestamp="2026-08-28 09:00:01",
            underlying_price=350.0,
            bid_price=349.9,
            ask_price=350.1,
            last_price=350.0,
            volume=10,
            seq_id=1,
            expiry="2026-09-04",
        )

        cmds = runtime.process_tick(tick_d3)
        # Track 1의 만기 D-4 컷오프 프로토콜로 인해 가두리 청산 주문이 생성됨을 확인
        self.assertIsNone(t1.active_fence, "Track 1 active fence should be cleared on DTE <= 4.0")
        self.assertTrue(any(c.track_id == "Track1" and c.side.value == "BUY" for c in cmds))


if __name__ == "__main__":
    unittest.main()
