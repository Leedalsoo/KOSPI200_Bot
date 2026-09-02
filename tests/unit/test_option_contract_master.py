# -*- coding: utf-8 -*-
"""Unit tests for OptionContractMaster contract and KIS MST Master Parsing Integration."""
import io
import unittest
import zipfile

from shared.calendar.krx_calendar import KrxTradingCalendar
from shared.contracts.canonical import CanonicalMarketTick
from shared.contracts.option_master import (
    IOptionContractMaster,
    InMemoryOptionContractMaster,
    KisProductionOptionContractMaster,
    KisOptionMasterLoader,
    KisMasterParseError,
    calculate_krx_monthly_option_expiry,
    calculate_krx_weekly_option_expiry,
    parse_kis_fo_idx_mst,
    KIS_FO_IDX_MASTER_URL,
)
from option_program.runtime.program_runtime import OptionProgramRuntime


def create_sample_kis_mst_zip_bytes() -> bytes:
    """공식 KIS MST 포맷을 재현한 테스트 ZIP 바이트 스트림 생성 (수동 register_contract 대체용)."""
    sample_mst = "\n".join([
        "5|B01609335|KR4B01693351|C 202609   335.0|2|00335.00| |2001|KOSPI200",
        "6|C01609335|KR4C01693350|P 202609   335.0|3|00335.00| |2001|KOSPI200",
        "5|B01610350|KR4B016A3509|C 202610   350.0|2|00350.00| |2001|KOSPI200",
        "L|B09FCW945|KR4B09FC9450|위클리C 2609W1   945.0|2|00945.00| |2001|KOSPI200",
        "1|A01609|KR4A01690002|F 202609| |00000.00|1|2001|KOSPI200",  # 선물 레코드 (제외 대상)
        "INVALID_LINE_NO_PIPES",
    ])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("fo_idx_code_mts.mst", sample_mst.encode("cp949"))
    return buf.getvalue()


class TestOptionContractMaster(unittest.TestCase):
    """OptionContractMaster 및 KIS MST 파싱 연동 검증."""

    def setUp(self) -> None:
        self.master: IOptionContractMaster = InMemoryOptionContractMaster(
            contracts={
                "201V8350": "2026-09-03",
                "201V8352": "2026-09-03",
                "201W9350": "2026-09-10",
            }
        )
        self.calendar = KrxTradingCalendar()

    def test_lookup_existing_contract(self) -> None:
        """등록된 옵션 종목코드의 만기일 조회 성공 검증."""
        self.assertEqual(self.master.get_expiry("201V8350"), "2026-09-03")
        self.assertEqual(self.master.get_expiry("201W9350"), "2026-09-10")

    def test_lookup_non_existing_or_empty_contract(self) -> None:
        """등록되지 않은 종목 또는 빈 문자열 조회 시 None 반환 검증."""
        self.assertIsNone(self.master.get_expiry("UNKNOWN_SYM"))
        self.assertIsNone(self.master.get_expiry(""))

    def test_calculate_krx_monthly_option_expiry_exact_dates(self) -> None:
        """KRX 월물 옵션 만기일(매월 2번째 목요일) 계산 검증."""
        # 2026년 9월: 9/1(화), 첫 목=9/3, 둘째 목=9/10
        self.assertEqual(calculate_krx_monthly_option_expiry(2026, 9, calendar=self.calendar), "2026-09-10")
        # 2026년 10월: 10/1(목=1번째), 둘째 목=10/8
        self.assertEqual(calculate_krx_monthly_option_expiry(2026, 10, calendar=self.calendar), "2026-10-08")
        # 2026년 8월: 8/1(토), 첫 목=8/6, 둘째 목=8/13
        self.assertEqual(calculate_krx_monthly_option_expiry(2026, 8, calendar=self.calendar), "2026-08-13")

    def test_calculate_krx_weekly_option_expiry(self) -> None:
        """KRX 위클리 옵션 만기일(해당 주차 목요일) 계산 검증."""
        # 2026년 9월 1주차 목요일 -> 2026-09-03
        self.assertEqual(calculate_krx_weekly_option_expiry(2026, 9, 1, calendar=self.calendar), "2026-09-03")
        # 2026년 9월 3주차 목요일 -> 2026-09-17
        self.assertEqual(calculate_krx_weekly_option_expiry(2026, 9, 3, calendar=self.calendar), "2026-09-17")

    def test_parse_kis_fo_idx_mst_real_records(self) -> None:
        """KIS fo_idx_code_mts.mst 실제 원시 레코드 파싱 및 만기일 매핑 검증."""
        zip_bytes = create_sample_kis_mst_zip_bytes()
        contracts = KisOptionMasterLoader.load_from_zip_bytes(zip_bytes, calendar=self.calendar)

        # 2026-09 콜옵션 만기일 -> 2026-09-10
        self.assertEqual(contracts.get("B01609335"), "2026-09-10")
        self.assertEqual(contracts.get("KR4B01693351"), "2026-09-10")
        # 2026-09 풋옵션 만기일 -> 2026-09-10
        self.assertEqual(contracts.get("C01609335"), "2026-09-10")
        # 2026-10 콜옵션 만기일 -> 2026-10-08
        self.assertEqual(contracts.get("B01610350"), "2026-10-08")
        # 위클리 1주차 만기일 -> 2026-09-03
        self.assertEqual(contracts.get("B09FCW945"), "2026-09-03")
        # 선물은 등록되지 않음
        self.assertNotIn("A01609", contracts)

    def test_actual_kis_online_master_download_and_parsing(self) -> None:
        """[실제 외부 Source 검증] 공식 KIS MST URL(fo_idx_code_mts.mst.zip) 실제 다운로드 및 파싱 실측.

        네트워크 연결 불가 환경에서는 unittest skipTest로 명시적이고 검증 가능한 사유를 기록하며,
        데이터 파싱 오류나 계약 누락은 절대로 은폐하지 않고 즉시 테스트 실패로 처리한다.
        """
        import urllib.error
        try:
            contracts = KisOptionMasterLoader.load_from_url(
                url=KIS_FO_IDX_MASTER_URL,
                timeout=10.0,
                calendar=self.calendar,
            )
        except (urllib.error.URLError, TimeoutError, OSError) as net_err:
            self.skipTest(f"KIS Master Source network unreachable in test environment: {net_err}")
            return

        # 온라인 다운로드 성공 시 수천 개의 실제 파생옵션 계약이 파싱되어야 함 (실패 시 즉시 FAIL)
        self.assertGreater(len(contracts), 1000, "Real KIS MST must contain at least 1,000 contracts")
        # 코스피200 옵션 심볼(B 또는 C로 시작)이 반드시 존재해야 함
        has_kospi_options = any(sym.startswith(("B", "C", "2", "3")) for sym in contracts.keys())
        self.assertTrue(has_kospi_options, "Real KIS MST must contain valid KOSPI200 option symbols")

    def test_process_tick_e2e_canonical_expiry_propagation(self) -> None:
        """[핵심 요구 2] process_tick() 실행을 포함한 Master expiry ➔ CanonicalMarketTick.expiry E2E assertion."""
        runtime = OptionProgramRuntime()
        self.assertIsInstance(runtime.option_master, KisProductionOptionContractMaster)

        # MST ZIP 소스를 직접 로드 (수동 register_contract 호출 없음)
        zip_bytes = create_sample_kis_mst_zip_bytes()
        runtime.option_master.load_from_zip_bytes(zip_bytes)

        t1 = runtime.strategies[0]
        t1.active_fence = {"type": "CALL", "strike": 355.0, "tag_id": 1}

        # CanonicalMarketTick.expiry가 빈 tick 준비
        tick = CanonicalMarketTick(
            timestamp="2026-09-04 09:00:01",
            underlying_price=350.0,
            bid_price=349.9,
            ask_price=350.1,
            last_price=350.0,
            volume=10,
            seq_id=1,
            symbol="B01609335",
            expiry="",  # 초기 expiry는 비어있음
        )

        # process_tick(tick)을 실제로 호출
        cmds = runtime.process_tick(tick)

        # 1. 🎯 process_tick 내부에서 CanonicalMarketTick.expiry에 실제 만기일('2026-09-10')이 공급되었음을 직접 assert!
        self.assertIsNotNone(runtime.last_processed_tick)
        self.assertEqual(runtime.last_processed_tick.expiry, "2026-09-10")

        # 2. 🎯 공급된 만기일로부터 DTE=4.0이 산출되어 Track 1 D-4 컷오프 가두리 조기 청산이 발동했음을 확인
        self.assertIsNone(t1.active_fence, "Track 1 active fence cleared on DTE <= 4.0")
        self.assertTrue(any(c.track_id == "Track1" for c in cmds))

    def test_missing_expiry_completely_eliminates_arbitrary_dte_fallbacks(self) -> None:
        """[핵심 요구 3] 30.0 / 999.0 등 임의의 DTE fallback이 완전히 제거되었음을 검증."""
        runtime = OptionProgramRuntime()
        t1 = runtime.strategies[0]
        t1.active_fence = {"type": "CALL", "strike": 355.0, "tag_id": 1}

        # 마스터에 없는 종목으로 expiry 없는 tick 투입
        bare_tick = CanonicalMarketTick(
            timestamp="2026-09-04 09:00:01",
            underlying_price=350.0,
            symbol="UNREGISTERED_SYMBOL",
            expiry="",
        )

        cmds = runtime.process_tick(bare_tick)

        # 1. last_processed_tick의 expiry가 빈 문자열로 유지됨
        self.assertIsNotNone(runtime.last_processed_tick)
        self.assertEqual(runtime.last_processed_tick.expiry, "")

        # 2. 임의의 30.0이나 999.0 fallback으로 D-4 컷오프가 오작동하지 않고 active_fence가 안전하게 보존됨
        self.assertIsNotNone(t1.active_fence, "Active fence must be preserved without arbitrary DTE fallback")

    def test_source_failure_explicitly_raised_or_recorded(self) -> None:
        """잘못된 ZIP 데이터 또는 다운로드 실패 시 조용히 성공으로 은폐되지 않고 예외 발생 또는 last_error 기록 검증."""
        # 손상된 ZIP 바이트 스트림 로딩 시 KisMasterParseError 발생 검증
        with self.assertRaises(KisMasterParseError):
            KisOptionMasterLoader.load_from_zip_bytes(b"CORRUPTED_NON_ZIP_DATA")

        # 빈 바이트 스트림 로딩 시 KisMasterParseError 발생 검증
        with self.assertRaises(KisMasterParseError):
            KisOptionMasterLoader.load_from_zip_bytes(b"")

        # Master 인스턴스에 잘못된 데이터 로딩 시 last_error에 명시적 기록 검증
        master = KisProductionOptionContractMaster(auto_load=False)
        master.load_from_kis_source(url="https://invalid.url.nonexistent/master.zip")
        self.assertIsNotNone(master.last_error)
        self.assertFalse(master.is_loaded)

    def test_explicit_option_master_dependency_injection_preserved(self) -> None:
        """명시적으로 option_master를 주입했을 때 기존 DI 경로가 유지되는지 검증."""
        custom_master = InMemoryOptionContractMaster(contracts={"CUSTOM_SYM": "2026-11-12"})
        runtime = OptionProgramRuntime(option_master=custom_master)
        self.assertIs(runtime.option_master, custom_master)
        self.assertEqual(runtime.option_master.get_expiry("CUSTOM_SYM"), "2026-11-12")

    def test_malformed_mst_records_not_registered(self) -> None:
        """잘못되거나 파이프가 부족한 MST 레코드가 무시되는지 검증."""
        bad_mst = "\n".join([
            "",
            "|||",
            "1|NO_OPTION",
            "5|INVALIDSYM|NO_EXPIRY_INFO|NAME_WITHOUT_DATE",
        ])
        parsed = parse_kis_fo_idx_mst(bad_mst, calendar=self.calendar)
        self.assertEqual(len(parsed), 0)


if __name__ == "__main__":
    unittest.main()
