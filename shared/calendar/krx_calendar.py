# -*- coding: utf-8 -*-
"""KRX Trading Calendar Domain Interface and Engine.

Provides minimal, deterministic trading day evaluation, week-start detection,
and trading day counting for the KOSPI200 derivatives trading infrastructure.
"""
import logging
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Union

import orjson as json

logger = logging.getLogger(__name__)

# KIS 국내휴장일조회 공식 TR 정보
KIS_HOLIDAY_TR_ID: str = "CTCA0903R"
KIS_HOLIDAY_PATH: str = "/uapi/domestic-stock/v1/quotations/chk-holiday"


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

    @property
    def is_holiday_source_loaded(self) -> bool:
        """휴장일 Source가 공식 공급되어 정상 로드되었는지 확인."""
        if hasattr(self.holiday_provider, "is_loaded"):
            return bool(getattr(self.holiday_provider, "is_loaded"))
        if isinstance(self.holiday_provider, InMemoryHolidayProvider):
            return len(self.holiday_provider._holidays) > 0
        return False


class KisHolidaySourceError(Exception):
    """KIS 공식 휴장일 소스 조회/처리 기본 예외."""
    pass


class KisHolidayDownloadError(KisHolidaySourceError):
    """KIS 휴장일 API 네트워크 통신 또는 HTTP 응답 오류."""
    pass


class KisHolidayParseError(KisHolidaySourceError):
    """KIS 휴장일 응답 데이터 파싱 오류."""
    pass


class KisHolidayUnavailableError(KisHolidaySourceError):
    """공식 KIS 휴장일 소스가 로드되지 않았거나 사용할 수 없을 때 발생."""
    pass


def parse_kis_holiday_output(output_list: List[Dict[str, Any]]) -> Set[date]:
    """KIS chk-holiday API output 레코드 목록에서 휴장일(opnd_yn == 'N')을 추출."""
    holidays: Set[date] = set()
    for item in output_list:
        if not isinstance(item, dict):
            continue
        # opnd_yn: 개장일 여부 ('Y': 개장, 'N': 휴장)
        if item.get("opnd_yn") == "N":
            dt_str = str(item.get("bass_dt", "")).strip()
            if len(dt_str) == 8 and dt_str.isdigit():
                y = int(dt_str[:4])
                m = int(dt_str[4:6])
                d = int(dt_str[6:8])
                holidays.add(date(y, m, d))
    return holidays


class KisProductionHolidayProvider(IHolidayDataProvider):
    """[실전 운영 구현체] 한국투자증권(KIS Developers) 국내휴장일조회(chk-holiday) 공식 API 기반 휴장일 공급자.
    
    특징:
    1. KIS 공식 국내휴장일조회 TR(CTCA0903R)을 호출하여 KRX 공식 개장/휴장일(opnd_yn) 수신.
    2. 기존 KISAuthManager OAuth2 인증 체계를 100% 재사용.
    3. 로드 실패 시 빈 세트로 은폐하지 않고 last_error에 명확한 실패 원인을 기록하며 is_loaded=False 유지.
    4. 외부 응답 데이터 직접 주입(load_from_response_data) 및 단위 테스트 격리 지원.
    """

    def __init__(
        self,
        holidays: Optional[Set[date]] = None,
        auth_manager: Optional[Any] = None,
        auto_load: bool = True,
        target_year: Optional[int] = None,
        strict_mode: bool = False,
    ) -> None:
        self._holidays: Set[date] = set(holidays or [])
        self._auth_manager: Optional[Any] = auth_manager
        self._last_error: Optional[str] = None
        self._target_year: int = target_year or date.today().year
        self.strict_mode: bool = strict_mode

        if auto_load and not self._holidays:
            self.load_from_kis_api(target_year=self._target_year)

    @property
    def is_loaded(self) -> bool:
        """휴장일 데이터가 성공적으로 1건 이상 로드되었는지 여부."""
        return len(self._holidays) > 0 and self._last_error is None

    @property
    def total_holidays(self) -> int:
        return len(self._holidays)

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    def is_holiday(self, target_date: date) -> bool:
        if self.strict_mode and not self.is_loaded:
            raise KisHolidayUnavailableError(
                f"KIS holiday source is unavailable (last_error: {self._last_error})."
            )
        return target_date in self._holidays

    def get_holidays_for_year(self, year: int) -> Set[date]:
        return {h for h in self._holidays if h.year == year}

    def load_from_response_data(self, resp_data: Dict[str, Any]) -> int:
        """KIS API 응답 딕셔너리로부터 휴장일 파싱 및 등록."""
        if not isinstance(resp_data, dict):
            self._last_error = "Invalid response format: expected dict"
            raise KisHolidayParseError(self._last_error)

        rt_cd = resp_data.get("rt_cd")
        if rt_cd != "0":
            msg_cd = resp_data.get("msg_cd") or ""
            msg1 = resp_data.get("msg1") or ""
            self._last_error = f"KIS API error (rt_cd={rt_cd}, msg_cd={msg_cd}): {msg1}".strip()
            raise KisHolidaySourceError(self._last_error)

        output = resp_data.get("output", [])
        if not isinstance(output, list):
            self._last_error = "Invalid output field: expected list"
            raise KisHolidayParseError(self._last_error)

        parsed = parse_kis_holiday_output(output)
        self._holidays.update(parsed)
        self._last_error = None
        logger.info(f"[KisProductionHolidayProvider] Loaded {len(parsed)} holidays from response data.")
        return len(parsed)

    def load_from_kis_api(self, target_year: Optional[int] = None) -> int:
        """KIS Developers chk-holiday API를 호출하여 공식 KRX 휴장일을 다운로드 및 등록."""
        year = target_year or self._target_year
        try:
            auth = self._auth_manager
            if auth is None:
                # KISAuthManager 기본 인스턴스 지연 생성
                try:
                    from option_program.broker.kis_auth import KISAuthManager
                    auth = KISAuthManager.from_env()
                    self._auth_manager = auth
                except Exception as e:
                    self._last_error = f"Failed to initialize KISAuthManager: {e}"
                    logger.warning(f"[KisProductionHolidayProvider] {self._last_error}")
                    return 0

            if not auth.has_credentials():
                self._last_error = "KIS credentials (AppKey/Secret) are missing."
                logger.warning(f"[KisProductionHolidayProvider] {self._last_error}")
                return 0

            base_url = auth.base_url
            endpoint = f"{base_url}{KIS_HOLIDAY_PATH}"
            headers = auth.get_auth_headers(tr_id=KIS_HOLIDAY_TR_ID)

            # 연간 수집: 1월 1일 기준 호출 및 연속조회 지원
            total_loaded = 0
            base_dt = f"{year}0101"
            ctx_area_nk = ""
            ctx_area_fk = ""

            for _ in range(15):  # 연간 약 12~14회 분할 수신 안전 상한
                query_params = {
                    "BASS_DT": base_dt,
                    "CTX_AREA_NK": ctx_area_nk,
                    "CTX_AREA_FK": ctx_area_fk,
                }
                url = f"{endpoint}?{urllib.parse.urlencode(query_params)}"
                req = urllib.request.Request(url, headers=headers, method="GET")

                with urllib.request.urlopen(req, timeout=auth.timeout) as resp:
                    raw_bytes = resp.read()
                    data = json.loads(raw_bytes.decode("utf-8"))

                loaded_batch = self.load_from_response_data(data)
                total_loaded += loaded_batch

                # 연속 조회 키 확인
                ctx_area_nk = str(data.get("ctx_area_nk", "")).strip()
                ctx_area_fk = str(data.get("ctx_area_fk", "")).strip()

                if not ctx_area_nk and not ctx_area_fk:
                    break

                output = data.get("output", [])
                if output and isinstance(output, list):
                    last_dt = output[-1].get("bass_dt", "")
                    if last_dt and str(last_dt).startswith(str(year + 1)):
                        # 다음 해로 넘어갔으면 종료
                        break
                    if last_dt:
                        base_dt = str(last_dt)

            self._last_error = None
            logger.info(f"[KisProductionHolidayProvider] Successfully loaded {total_loaded} holidays for year {year}.")
            return total_loaded

        except Exception as e:
            self._last_error = str(e)
            logger.warning(f"[KisProductionHolidayProvider] API load failed: {e}")
            return 0


def create_default_krx_calendar(
    holiday_provider: Optional[IHolidayDataProvider] = None,
    auto_load_kis: bool = True,
    auth_manager: Optional[Any] = None,
) -> KrxTradingCalendar:
    """Production 기본 KrxTradingCalendar 팩토리 함수."""
    provider = holiday_provider or KisProductionHolidayProvider(
        auth_manager=auth_manager,
        auto_load=auto_load_kis,
    )
    return KrxTradingCalendar(holiday_provider=provider)
