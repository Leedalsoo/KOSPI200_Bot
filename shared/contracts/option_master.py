# -*- coding: utf-8 -*-
"""Option Contract Master & Expiry Lookup Interface.

Defines the contract for looking up option expiration dates by instrument symbol,
and provides loaders for official KIS index futures/options master data (fo_idx_code_mts.mst).
"""
import io
import logging
import re
import urllib.request
import zipfile
from abc import ABC, abstractmethod
from datetime import date, timedelta
from typing import Dict, Optional

from shared.calendar.krx_calendar import KrxTradingCalendar

logger = logging.getLogger(__name__)

KIS_FO_IDX_MASTER_URL = "https://new.real.download.dws.co.kr/common/master/fo_idx_code_mts.mst.zip"


class KisMasterSourceError(Exception):
    """KIS 마스터 소스 다운로드 및 파싱 관련 기본 예외."""
    pass


class KisMasterDownloadError(KisMasterSourceError):
    """KIS 마스터 파일 다운로드 실패 시 발생하는 예외."""
    pass


class KisMasterParseError(KisMasterSourceError):
    """KIS 마스터 파일 압축 해제 또는 파싱 실패 시 발생하는 예외."""
    pass


def calculate_krx_monthly_option_expiry(
    year: int,
    month: int,
    calendar: Optional[KrxTradingCalendar] = None,
) -> str:
    """KRX 월물 옵션 만기일(매월 두 번째 목요일, 휴장일 시 직전 거래일) 계산."""
    first_day = date(year, month, 1)
    # 0: Mon, 1: Tue, 2: Wed, 3: Thu, 4: Fri, 5: Sat, 6: Sun
    first_day_weekday = first_day.weekday()
    first_thursday = 1 + (3 - first_day_weekday) % 7
    second_thursday = first_thursday + 7
    target_date = date(year, month, second_thursday)

    cal = calendar or KrxTradingCalendar()
    # 휴장일(공휴일)인 경우 직전 거래일로 조정
    while not cal.is_trading_day(target_date):
        target_date = cal.prev_trading_day(target_date)

    return target_date.strftime("%Y-%m-%d")


def calculate_krx_weekly_option_expiry(
    year: int,
    month: int,
    week_num: int,
    calendar: Optional[KrxTradingCalendar] = None,
) -> str:
    """KRX 위클리 옵션 만기일(해당 주차 목요일, 휴장일 시 직전 거래일) 계산."""
    first_day = date(year, month, 1)
    first_day_weekday = first_day.weekday()
    first_thursday = 1 + (3 - first_day_weekday) % 7
    target_day = first_thursday + (week_num - 1) * 7

    # 월말 초과 방어
    max_days = (date(year, month + 1, 1) - timedelta(days=1)).day if month < 12 else 31
    target_day = min(target_day, max_days)
    target_date = date(year, month, target_day)

    cal = calendar or KrxTradingCalendar()
    while not cal.is_trading_day(target_date):
        target_date = cal.prev_trading_day(target_date)

    return target_date.strftime("%Y-%m-%d")


def parse_kis_fo_idx_mst(
    raw_content: str,
    calendar: Optional[KrxTradingCalendar] = None,
) -> Dict[str, str]:
    """KIS 공식 fo_idx_code_mts.mst 텍스트 내용을 파싱하여 {symbol: expiry_date} 매핑 생성."""
    if not raw_content or not raw_content.strip():
        return {}

    contracts: Dict[str, str] = {}
    cal = calendar or KrxTradingCalendar()

    # 정규식 패턴: 6자리 연월 (예: 202609)
    month_pattern = re.compile(r"20\d{4}")
    # 위클리 패턴: 2609W1 등 (예: 2609W1 -> 2026년 9월 1주차)
    weekly_pattern = re.compile(r"(\d{2})(\d{2})W(\d)")

    for line in raw_content.splitlines():
        if not line or "|" not in line:
            continue
        parts = line.split("|")
        if len(parts) < 4:
            continue

        prod_type = parts[0].strip()
        symbol = parts[1].strip()
        standard_code = parts[2].strip()
        name = parts[3].strip()

        # 옵션 상품 타입 필터링: 5(Call), 6(Put), D(미니Call), E(미니Put), L/M/N/O/P/Q/R/S(위클리)
        # 또는 심볼이 2, 3, B, C로 시작하는 옵션
        is_option = (
            prod_type in ("5", "6", "D", "E", "L", "M", "N", "O", "P", "Q", "R", "S")
            or symbol.startswith(("2", "3", "B", "C"))
            or " C " in name
            or " P " in name
            or "Call" in name
            or "Put" in name
        )
        if not is_option:
            continue

        expiry_date: Optional[str] = None

        # 1. 위클리 옵션 확인
        weekly_m = weekly_pattern.search(name) or weekly_pattern.search(symbol)
        if weekly_m:
            try:
                y = 2000 + int(weekly_m.group(1))
                m = int(weekly_m.group(2))
                w = int(weekly_m.group(3))
                expiry_date = calculate_krx_weekly_option_expiry(y, m, w, calendar=cal)
            except Exception as e:
                logger.debug(f"Weekly option parse note ({name}): {e}")

        # 2. 일반 월물 옵션 확인
        if not expiry_date:
            month_m = month_pattern.search(name)
            if month_m:
                try:
                    ym_str = month_m.group(0)
                    y = int(ym_str[:4])
                    m = int(ym_str[4:6])
                    if 1 <= m <= 12:
                        expiry_date = calculate_krx_monthly_option_expiry(y, m, calendar=cal)
                except Exception as e:
                    logger.debug(f"Monthly option parse note ({name}): {e}")

        if symbol and expiry_date:
            contracts[symbol] = expiry_date
            if standard_code:
                contracts[standard_code] = expiry_date

    return contracts


class KisOptionMasterLoader:
    """KIS 공식 지수선물옵션 마스터 다운로드 및 파싱 로더."""

    @staticmethod
    def load_from_zip_bytes(
        zip_bytes: bytes,
        calendar: Optional[KrxTradingCalendar] = None,
    ) -> Dict[str, str]:
        """ZIP 바이트 스트림에서 fo_idx_code_mts.mst 압축을 풀고 파싱."""
        if not zip_bytes:
            raise KisMasterParseError("Empty zip bytes provided for KIS master loading.")
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
                # fo_idx_code_mts.mst 우선 탐색
                target_fn = None
                for fn in z.namelist():
                    if "fo_idx_code_mts" in fn or "fo_idx_code" in fn or "optcode" in fn:
                        target_fn = fn
                        break
                if not target_fn and z.namelist():
                    target_fn = z.namelist()[0]

                if not target_fn:
                    raise KisMasterParseError("No valid master file found in zip archive.")

                raw_bytes = z.read(target_fn)
                raw_text = raw_bytes.decode("cp949", errors="ignore")
                parsed = parse_kis_fo_idx_mst(raw_text, calendar=calendar)
                if not parsed:
                    raise KisMasterParseError(f"Master file '{target_fn}' parsed 0 contracts.")
                return parsed
        except Exception as e:
            if isinstance(e, KisMasterParseError):
                raise
            raise KisMasterParseError(f"Failed to extract and parse zip archive: {e}") from e

    @classmethod
    def load_from_url(
        cls,
        url: str = KIS_FO_IDX_MASTER_URL,
        timeout: float = 10.0,
        calendar: Optional[KrxTradingCalendar] = None,
    ) -> Dict[str, str]:
        """공식 KIS 마스터 서버에서 다운로드하여 파싱."""
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
                return cls.load_from_zip_bytes(data, calendar=calendar)
        except Exception as exc:
            raise KisMasterDownloadError(f"Failed to download KIS master from {url}: {exc}") from exc


class IOptionContractMaster(ABC):
    """[추상 인터페이스] 옵션 종목 심볼 기반 만기일 조회 계약."""

    @abstractmethod
    def get_expiry(self, symbol: str) -> Optional[str]:
        """주어진 옵션 종목코드(symbol)의 만기일(YYYY-MM-DD)을 반환.

        종목코드가 존재하지 않거나 만기일이 정의되지 않은 경우 None 반환.
        """
        pass

    @abstractmethod
    def register_contract(self, symbol: str, expiry: str) -> None:
        """옵션 종목코드와 만기일을 마스터 테이블에 등록."""
        pass


class InMemoryOptionContractMaster(IOptionContractMaster):
    """[기본 구현체] 메모리 기반 옵션 종목 마스터 테이블."""

    def __init__(
        self,
        contracts: Optional[Dict[str, str]] = None,
        auto_load_kis_source: bool = False,
        calendar: Optional[KrxTradingCalendar] = None,
    ) -> None:
        # {symbol: expiry_date_str (YYYY-MM-DD)}
        self._contracts: Dict[str, str] = dict(contracts or {})
        self.last_error: Optional[str] = None
        if auto_load_kis_source and not self._contracts:
            self.load_from_kis_source(calendar=calendar)

    def get_expiry(self, symbol: str) -> Optional[str]:
        if not symbol:
            return None
        return self._contracts.get(symbol.strip())

    def register_contract(self, symbol: str, expiry: str) -> None:
        if symbol and expiry:
            self._contracts[symbol.strip()] = expiry.strip()

    def load_from_kis_source(
        self,
        calendar: Optional[KrxTradingCalendar] = None,
        url: str = KIS_FO_IDX_MASTER_URL,
    ) -> int:
        """공식 KIS 마스터 소스를 다운로드하여 등록."""
        try:
            loaded = KisOptionMasterLoader.load_from_url(url=url, calendar=calendar)
            self._contracts.update(loaded)
            self.last_error = None
            logger.info(f"[InMemoryOptionContractMaster] Loaded {len(loaded)} contracts from KIS source.")
            return len(loaded)
        except Exception as e:
            self.last_error = str(e)
            logger.warning(f"[InMemoryOptionContractMaster] KIS source load note: {e}")
            return 0

    def load_from_raw_mst_content(
        self,
        raw_text: str,
        calendar: Optional[KrxTradingCalendar] = None,
    ) -> int:
        """원시 MST 텍스트로부터 파싱하여 등록."""
        parsed = parse_kis_fo_idx_mst(raw_text, calendar=calendar)
        self._contracts.update(parsed)
        return len(parsed)

    @property
    def total_contracts(self) -> int:
        return len(self._contracts)


class KisProductionOptionContractMaster(IOptionContractMaster):
    """[실전 운영 구현체] KIS 공식 fo_idx_code_mts.mst 기반 옵션 마스터."""

    def __init__(
        self,
        contracts: Optional[Dict[str, str]] = None,
        calendar: Optional[KrxTradingCalendar] = None,
        auto_load: bool = True,
        url: str = KIS_FO_IDX_MASTER_URL,
    ) -> None:
        self.calendar: KrxTradingCalendar = calendar or KrxTradingCalendar()
        self._contracts: Dict[str, str] = dict(contracts or {})
        self.last_error: Optional[str] = None
        self.is_loaded: bool = len(self._contracts) > 0
        if auto_load and not self._contracts:
            self.load_from_kis_source(url=url)

    def get_expiry(self, symbol: str) -> Optional[str]:
        if not symbol:
            return None
        return self._contracts.get(symbol.strip())

    def register_contract(self, symbol: str, expiry: str) -> None:
        if symbol and expiry:
            self._contracts[symbol.strip()] = expiry.strip()

    def load_from_kis_source(self, url: str = KIS_FO_IDX_MASTER_URL) -> int:
        """공식 KIS 마스터 소스를 다운로드하여 등록."""
        try:
            loaded = KisOptionMasterLoader.load_from_url(url=url, calendar=self.calendar)
            self._contracts.update(loaded)
            self.is_loaded = len(self._contracts) > 0
            self.last_error = None
            logger.info(f"[KisProductionOptionContractMaster] Loaded {len(loaded)} contracts from KIS source.")
            return len(loaded)
        except Exception as e:
            self.last_error = str(e)
            logger.warning(f"[KisProductionOptionContractMaster] Source download note: {e}")
            return 0

    def load_from_raw_mst_content(self, raw_text: str) -> int:
        """원시 MST 텍스트로부터 파싱하여 등록."""
        parsed = parse_kis_fo_idx_mst(raw_text, calendar=self.calendar)
        self._contracts.update(parsed)
        self.is_loaded = len(self._contracts) > 0
        return len(parsed)

    def load_from_zip_bytes(self, zip_bytes: bytes) -> int:
        """ZIP 바이트 스트림으로부터 파싱하여 등록."""
        parsed = KisOptionMasterLoader.load_from_zip_bytes(zip_bytes, calendar=self.calendar)
        self._contracts.update(parsed)
        self.is_loaded = len(self._contracts) > 0
        return len(parsed)

    @property
    def total_contracts(self) -> int:
        return len(self._contracts)


def create_default_option_master(
    calendar: Optional[KrxTradingCalendar] = None,
    contracts: Optional[Dict[str, str]] = None,
    auto_load_kis: bool = True,
) -> IOptionContractMaster:
    """Production 기본 OptionContractMaster 팩토리 함수."""
    return KisProductionOptionContractMaster(
        contracts=contracts,
        calendar=calendar,
        auto_load=auto_load_kis,
    )
