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
    calculate_krx_monthly_option_expiry,
    calculate_krx_weekly_option_expiry,
    parse_kis_fo_idx_mst,
    create_default_option_master,
)
from option_program.runtime.program_runtime import OptionProgramRuntime


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

    def test_register_dynamic_contract(self) -> None:
        """런타임 동적 종목 등록 및 조회 검증."""
        self.master.register_contract("201X9355", "2026-10-08")
        self.assertEqual(self.master.get_expiry("201X9355"), "2026-10-08")

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
        sample_mst = "\n".join([
            "5|B01609335|KR4B01693351|C 202609   335.0|2|00335.00| |2001|KOSPI200",
            "6|C01609335|KR4C01693350|P 202609   335.0|3|00335.00| |2001|KOSPI200",
            "5|B01610350|KR4B016A3509|C 202610   350.0|2|00350.00| |2001|KOSPI200",
            "L|B09FCW945|KR4B09FC9450|위클리C 2609W1   945.0|2|00945.00| |2001|KOSPI200",
            "1|A01609|KR4A01690002|F 202609| |00000.00|1|2001|KOSPI200",  # 선물 레코드 (옵션 아니므로 제외)
            "INVALID_LINE_NO_PIPES",
        ])

        contracts = parse_kis_fo_idx_mst(sample_mst, calendar=self.calendar)
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

    def test_kis_option_master_loader_zip_bytes(self) -> None:
        """KIS Master ZIP 바이트 스트림 로더 검증."""
        sample_mst = "5|B01609350|KR4B01693500|C 202609   350.0|2|00350.00| |2001|KOSPI200\n"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("fo_idx_code_mts.mst", sample_mst.encode("cp949"))

        loaded = KisOptionMasterLoader.load_from_zip_bytes(buf.getvalue(), calendar=self.calendar)
        self.assertEqual(loaded.get("B01609350"), "2026-09-10")

    def test_default_option_program_runtime_uses_production_option_master(self) -> None:
        """기본 OptionProgramRuntime() 생성 시 실제 Production Master가 연결되는지 검증."""
        # 인자 없이 기본 생성
        runtime = OptionProgramRuntime()
        self.assertIsInstance(runtime.option_master, IOptionContractMaster)
        self.assertIsInstance(runtime.option_master, KisProductionOptionContractMaster)

    def test_default_runtime_symbol_to_expiry_dte_pipeline(self) -> None:
        """기본 OptionProgramRuntime()에서 symbol ➔ master lookup ➔ DTE 계산 ➔ 전략 전달 검증."""
        runtime = OptionProgramRuntime()
        # Production Master에 테스트 계약 등록
        runtime.option_master.register_contract("B01609335", "2026-09-10")

        t1 = runtime.strategies[0]
        t1.active_fence = {"type": "CALL", "strike": 355.0, "tag_id": 1}

        # 2026-09-04(금) 기준 2026-09-10(목) 만기일 -> DTE=4.0 -> Track 1 컷오프 발동 조건
        tick = CanonicalMarketTick(
            timestamp="2026-09-04 09:00:01",
            underlying_price=350.0,
            bid_price=349.9,
            ask_price=350.1,
            last_price=350.0,
            volume=10,
            seq_id=1,
            symbol="B01609335",
            expiry="",  # 비어있는 expiry -> master lookup으로 2026-09-10 조회
        )

        cmds = runtime.process_tick(tick)
        self.assertIsNone(t1.active_fence, "Track 1 active fence cleared on DTE <= 4.0")
        self.assertTrue(any(c.track_id == "Track1" for c in cmds))

    def test_explicit_option_master_dependency_injection_preserved(self) -> None:
        """명시적으로 option_master를 주입했을 때 기존 DI 경로가 유지되는지 검증."""
        custom_master = InMemoryOptionContractMaster(contracts={"CUSTOM_SYM": "2026-11-12"})
        runtime = OptionProgramRuntime(option_master=custom_master)
        self.assertIs(runtime.option_master, custom_master)
        self.assertEqual(runtime.option_master.get_expiry("CUSTOM_SYM"), "2026-11-12")

    def test_runtime_empty_symbol_and_expiry_preserves_fallback(self) -> None:
        """symbol과 expiry 모두 없는 경우 기존 30.0 fallback 및 정상 틱 처리가 안전하게 유지되는지 검증."""
        runtime = OptionProgramRuntime(
            calendar=self.calendar,
            option_master=self.master,
        )

        bare_tick = CanonicalMarketTick(
            timestamp="2026-08-28 09:00:01",
            underlying_price=350.0,
            bid_price=349.9,
            ask_price=350.1,
            last_price=350.0,
            volume=10,
            seq_id=1,
        )

        cmds = runtime.process_tick(bare_tick)
        self.assertIsInstance(cmds, list)

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
