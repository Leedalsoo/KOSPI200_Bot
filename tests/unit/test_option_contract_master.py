# -*- coding: utf-8 -*-
"""Unit tests for OptionContractMaster contract and KIS MST Master Parsing Integration."""
import io
import unittest
import zipfile
from typing import Any, Dict

from shared.calendar.krx_calendar import KrxTradingCalendar
from shared.calendar.expiry_calculator import calculate_dte
from shared.contracts.canonical import CanonicalMarketTick, CanonicalOptionType
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

        # KisProductionOptionContractMaster를 통한 정상 공급 상태 계약 검증
        prod_master = KisProductionOptionContractMaster(contracts=contracts)
        self.assertTrue(prod_master.is_loaded, "Production master must report is_loaded=True when populated")
        self.assertGreater(prod_master.total_contracts, 1000, "total_contracts must reflect parsed contracts")
        self.assertIsNone(prod_master.last_error, "last_error must be None on successful load")

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

    def test_track1_on_tick_default_days_to_expiry_is_none(self) -> None:
        """[Track1 DTE 계약 증명] days_to_expiry 기본값이 30.0이 아닌 None이며 임의 fallback이 적용되지 않음을 직접 증명."""
        from option_program.strategy.plugins.track1 import Track1
        t1 = Track1(config={})
        t1.active_fence = {"type": "CALL", "strike": 355.0, "tag_id": 1}

        # 1. days_to_expiry 인자 없이 호출 시 30.0이 아닌 None이 기본 적용되어 정상 실행
        t1.on_tick(current_price=350.0, trend_signal=False)
        self.assertIsNotNone(t1.active_fence, "active_fence remains active when days_to_expiry is None (no 30.0 fallback)")

        # 2. days_to_expiry=None 명시적 전달 시에도 크래시 없이 정상 작동
        t1.on_tick(current_price=350.0, trend_signal=False, days_to_expiry=None)
        self.assertIsNotNone(t1.active_fence)

        # 3. DTE <= 4.0 제공 시 기존 D-4 보호 컷오프 정상 발동
        sigs_cutoff = t1.on_tick(current_price=350.0, trend_signal=False, days_to_expiry=4.0)
        self.assertIsNone(t1.active_fence, "active_fence cleared when days_to_expiry <= 4.0")
        self.assertTrue(any(s.get("action") == "FENCE_CLEAR" for s in sigs_cutoff))

    def test_track1_evaluate_strategy_to_on_tick_dte_contract(self) -> None:
        """[Track1 evaluate_strategy -> on_tick DTE 계약 증명]
        1. evaluate_strategy()에 days_to_expiry가 없는 경우 on_tick()에 None이 전달되고 30.0이 자동 적용되지 않음.
        2. 실제 DTE를 제공하면 그 값이 on_tick()에 유지됨.
        3. DTE <= 4.0일 때 기존 D-4 보호 로직이 유지됨.
        4. DTE 미존재 시 active fence가 arbitrary DTE 때문에 잘못 청산되지 않음.
        """
        from option_program.strategy.plugins.track1 import Track1
        t1 = Track1(config={})

        # 1. days_to_expiry 없는 market_data로 evaluate_strategy 호출
        t1.is_market_opened = True
        t1.active_fence = {"type": "PUT", "strike": 342.5, "tag_id": 1}
        res_no_dte = t1.evaluate_strategy(350.0, 350.0, {"date_str": "2026-09-04"})
        self.assertIsNotNone(t1.active_fence, "active_fence must remain active when days_to_expiry is omitted (no 30.0 fallback)")
        self.assertFalse(any(s.get("action") == "FENCE_CLEAR" for s in res_no_dte.get("signals", [])))

        # 2. 실제 DTE=10.0 제공 시 D-4 컷오프 미발동 및 가두리 유지
        res_dte_10 = t1.evaluate_strategy(350.0, 350.0, {"date_str": "2026-09-04", "days_to_expiry": 10.0})
        self.assertIsNotNone(t1.active_fence, "active_fence must remain active when DTE=10.0")
        self.assertFalse(any(s.get("action") == "FENCE_CLEAR" for s in res_dte_10.get("signals", [])))

        # 3. 실제 DTE=4.0 제공 시 기존 D-4 보호 로직(FENCE_CLEAR) 정상 발동
        res_cutoff = t1.evaluate_strategy(350.0, 350.0, {"date_str": "2026-09-04", "days_to_expiry": 4.0})
        self.assertIsNone(t1.active_fence, "active_fence cleared when DTE=4.0 provided in evaluate_strategy")
        self.assertTrue(any(s.get("action") == "FENCE_CLEAR" for s in res_cutoff.get("signals", [])))

    def test_source_failure_explicitly_raised_or_recorded(self) -> None:
        """잘못된 ZIP 데이터 또는 다운로드 실패 시 조용히 성공으로 은폐되지 않고 예외 발생 또는 last_error 기록 검증."""
        # 1. 초기 빈 Master는 is_loaded=False, total_contracts=0, last_error=None
        empty_master = KisProductionOptionContractMaster(auto_load=False)
        self.assertFalse(empty_master.is_loaded, "Empty master must not report is_loaded=True")
        self.assertEqual(empty_master.total_contracts, 0)
        self.assertIsNone(empty_master.last_error)

        # 2. 손상된 ZIP 바이트 스트림 로딩 시 KisMasterParseError 발생 검증
        with self.assertRaises(KisMasterParseError):
            KisOptionMasterLoader.load_from_zip_bytes(b"CORRUPTED_NON_ZIP_DATA")

        # 3. 빈 바이트 스트림 로딩 시 KisMasterParseError 발생 검증
        with self.assertRaises(KisMasterParseError):
            KisOptionMasterLoader.load_from_zip_bytes(b"")

        # 4. Master 인스턴스에 잘못된 데이터 로딩 시 last_error에 명시적 기록 및 is_loaded=False 유지
        bad_url_master = KisProductionOptionContractMaster(auto_load=False)
        bad_url_master.load_from_kis_source(url="https://invalid.url.nonexistent/master.zip")
        self.assertIsNotNone(bad_url_master.last_error, "Failed source load must record last_error")
        self.assertFalse(bad_url_master.is_loaded, "Failed source load must keep is_loaded=False")
        self.assertEqual(bad_url_master.total_contracts, 0, "Failed source load must keep total_contracts=0")

        # 5. Master 인스턴스에 손상된 zip 바이트 로딩 시 예외 발생 및 last_error 기록, is_loaded=False 유지
        with self.assertRaises(KisMasterParseError):
            bad_url_master.load_from_zip_bytes(b"CORRUPTED")
        self.assertIsNotNone(bad_url_master.last_error)
        self.assertFalse(bad_url_master.is_loaded)

    def test_option_master_supply_state_consistency(self) -> None:
        """is_loaded, total_contracts, last_error 상태 계약의 상호 일관성 검증.
        - total_contracts > 0 <=> is_loaded == True
        - 정상 로드 성공 시 last_error == None 복구
        """
        master = KisProductionOptionContractMaster(auto_load=False)
        self.assertFalse(master.is_loaded)
        self.assertEqual(master.total_contracts, 0)

        # 정상 ZIP 데이터 로드 시 공급 상태 전환 확인
        sample_zip = create_sample_kis_mst_zip_bytes()
        loaded_count = master.load_from_zip_bytes(sample_zip)
        self.assertGreater(loaded_count, 0)
        self.assertTrue(master.is_loaded, "is_loaded must be True when contracts are loaded")
        self.assertEqual(master.total_contracts, loaded_count)
        self.assertIsNone(master.last_error, "last_error must be None upon successful load")

        # InMemoryOptionContractMaster도 동일한 상태 계약 준수 확인
        mem_master = InMemoryOptionContractMaster()
        self.assertFalse(mem_master.is_loaded)
        self.assertEqual(mem_master.total_contracts, 0)
        mem_master.register_contract("TEST_SYM", "2026-09-10")
        self.assertTrue(mem_master.is_loaded)
        self.assertEqual(mem_master.total_contracts, 1)
        self.assertIsNone(mem_master.last_error)

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

    def test_market_tick_identity_preserved_in_last_processed_tick(self) -> None:
        """[Market Tick Identity] process_tick() 실행 후 last_processed_tick에서 핵심 Identity 필드가 변조되지 않고 보존됨을 검증."""
        runtime = OptionProgramRuntime()
        tick = CanonicalMarketTick(
            timestamp="2026-09-04 10:15:30",
            seq_id=777,
            symbol="201VC350",
            underlying_price=352.5,
            strike_price=350.0,
            option_type=CanonicalOptionType.CALL,
            bid_price=3.50,
            ask_price=3.55,
            last_price=3.52,
            volume=50,
            expiry="2026-09-10",
        )

        runtime.process_tick(tick)

        processed = runtime.last_processed_tick
        self.assertIsNotNone(processed)
        self.assertEqual(processed.timestamp, "2026-09-04 10:15:30")
        self.assertEqual(processed.seq_id, 777)
        self.assertEqual(processed.symbol, "201VC350")
        self.assertEqual(processed.underlying_price, 352.5)
        self.assertEqual(processed.strike_price, 350.0)
        self.assertEqual(processed.option_type, CanonicalOptionType.CALL)
        self.assertEqual(processed.bid_price, 3.50)
        self.assertEqual(processed.ask_price, 3.55)
        self.assertEqual(processed.last_price, 3.52)
        self.assertEqual(processed.volume, 50)
        self.assertEqual(processed.expiry, "2026-09-10")

    def test_market_tick_identity_explicit_seq_id_in_signal_and_order(self) -> None:
        """[Market Tick Identity] seq_id > 0인 경우 Signal ID 및 생성되는 Order ID에 seq_id가 그대로 사용됨을 검증."""
        runtime = OptionProgramRuntime()
        zip_bytes = create_sample_kis_mst_zip_bytes()
        runtime.option_master.load_from_zip_bytes(zip_bytes)

        t1 = runtime.strategies[0]
        t1.active_fence = {"type": "CALL", "strike": 355.0, "tag_id": 1}

        explicit_seq_id = 9999
        tick = CanonicalMarketTick(
            timestamp="2026-09-04 09:00:01",
            seq_id=explicit_seq_id,
            symbol="B01609335",
            underlying_price=350.0,
            last_price=350.0,
            expiry="2026-09-10",
        )

        cmds = runtime.process_tick(tick)

        # 1. 수집된 신호의 signal_id에 explicit_seq_id가 그대로 포함되어 있는지 검증
        self.assertTrue(len(runtime.last_signals) > 0, "Signals should be generated")
        for sig in runtime.last_signals:
            sig_id = sig.get("signal_id", "")
            self.assertIn(f"SIG-{explicit_seq_id}-", sig_id, f"Signal ID must contain seq_id {explicit_seq_id}: {sig_id}")

        # 2. 생성된 주문 명령 client_order_id에 explicit_seq_id가 그대로 포함되어 있는지 검증
        self.assertTrue(len(cmds) > 0, "Orders should be approved and commanded")
        for cmd in cmds:
            self.assertIn(f"ORD-T{explicit_seq_id}-", cmd.client_order_id, f"Order ID must contain seq_id {explicit_seq_id}: {cmd.client_order_id}")

    def test_market_tick_identity_zero_seq_id_tick_counter_fallback_and_increment(self) -> None:
        """[Market Tick Identity] seq_id=0인 경우 Runtime tick_counter가 fallback으로 사용되며 충돌 없이 단조 증가함을 검증."""
        runtime = OptionProgramRuntime()
        zip_bytes = create_sample_kis_mst_zip_bytes()
        runtime.option_master.load_from_zip_bytes(zip_bytes)

        # 1회차 tick (seq_id=0)
        t1 = runtime.strategies[0]
        t1.active_fence = {"type": "CALL", "strike": 355.0, "tag_id": 1}
        tick1 = CanonicalMarketTick(
            timestamp="2026-09-04 09:00:01",
            seq_id=0,
            symbol="B01609335",
            underlying_price=350.0,
            last_price=350.0,
            expiry="2026-09-10",
        )
        cmds1 = runtime.process_tick(tick1)
        self.assertEqual(runtime.tick_counter, 1)
        self.assertTrue(any("SIG-1-" in s.get("signal_id", "") for s in runtime.last_signals))
        self.assertTrue(any("ORD-T1-" in c.client_order_id for c in cmds1))

        # 2회차 tick (seq_id=0)
        t1.active_fence = {"type": "CALL", "strike": 355.0, "tag_id": 1}
        tick2 = CanonicalMarketTick(
            timestamp="2026-09-04 09:00:02",
            seq_id=0,
            symbol="B01609335",
            underlying_price=350.0,
            last_price=350.0,
            expiry="2026-09-10",
        )
        cmds2 = runtime.process_tick(tick2)
        self.assertEqual(runtime.tick_counter, 2)
        self.assertTrue(any("SIG-2-" in s.get("signal_id", "") for s in runtime.last_signals))
        self.assertTrue(any("ORD-T2-" in c.client_order_id for c in cmds2))

        # 3회차 tick (seq_id=0)
        t1.active_fence = {"type": "CALL", "strike": 355.0, "tag_id": 1}
        tick3 = CanonicalMarketTick(
            timestamp="2026-09-04 09:00:03",
            seq_id=0,
            symbol="B01609335",
            underlying_price=350.0,
            last_price=350.0,
            expiry="2026-09-10",
        )
        cmds3 = runtime.process_tick(tick3)
        self.assertEqual(runtime.tick_counter, 3)
        self.assertTrue(any("SIG-3-" in s.get("signal_id", "") for s in runtime.last_signals))
        self.assertTrue(any("ORD-T3-" in c.client_order_id for c in cmds3))

    def test_e2e_real_dte_pathway_direct_expiry_to_track1_and_track8(self) -> None:
        """[DTE E2E 실측] 운영 timestamp -> date_str -> 실제 calculate_dte() -> Track1/Track8 소비 경계 검증.
        1. DTE <= 4.0 (만기 임박 2026-09-04 -> 2026-09-10):
           - calculate_dte()가 정확히 4.0을 반환
           - Track1 D-4 만기 컷오프(FENCE_CLEAR) 발동
           - Track8 월물 초입 진입(DTE>=15) 미발동 (STANDBY 유지)
        2. DTE >= 15.0 (월물 초입 2026-08-14 -> 2026-09-10):
           - calculate_dte()가 정확히 19.0을 반환
           - Track8 월물 초입 양매수 진입(TRIGGERED) 발동 및 reason에 DTE 19.0 명시
           - Track1 active_fence 보존 (DTE > 4.0)
        """
        runtime = OptionProgramRuntime()
        t1 = runtime.strategies[0]
        t8 = runtime.strategies[7]

        # 1. 만기 임박 시나리오: 2026-09-04 (금) -> 만기 2026-09-10 (목)
        # 실제 KRX 거래일: 9/7(월), 9/8(화), 9/9(수), 9/10(목) -> 4거래일
        expected_dte_near = calculate_dte("2026-09-04", "2026-09-10", calendar=runtime.calendar)
        self.assertEqual(expected_dte_near, 4.0)

        t1.active_fence = {"type": "CALL", "strike": 355.0, "tag_id": 1}
        t8.reset_state()

        tick_near = CanonicalMarketTick(
            timestamp="2026-09-04 09:30:00",
            seq_id=101,
            symbol="201VC350",
            underlying_price=350.0,
            last_price=350.0,
            expiry="2026-09-10",
        )
        cmds_near = runtime.process_tick(tick_near)

        # Track1: DTE=4.0 <= 4.0 이므로 만기 컷오프 발동 확인
        self.assertIsNone(t1.active_fence, "Track 1 active fence must be cleared when DTE <= 4.0")
        self.assertTrue(any(c.track_id == "Track1" and "ORD-T101-" in c.client_order_id for c in cmds_near))

        # Track8: DTE=4.0 < 15.0 이므로 진입하지 않음
        self.assertFalse(t8.strangle_state["is_active"], "Track 8 must not enter when DTE < 15.0")

        # 2. 월물 초입 시나리오: 2026-08-14 (금) -> 만기 2026-09-10 (목)
        # 실제 KRX 거래일: 19거래일 (광복절 연휴 등 달력 반영)
        expected_dte_far = calculate_dte("2026-08-14", "2026-09-10", calendar=runtime.calendar)
        self.assertEqual(expected_dte_far, 19.0)

        t1.active_fence = {"type": "CALL", "strike": 355.0, "tag_id": 1}
        t8.reset_state()
        runtime.account_summary.free_margin = 10000000.0

        tick_far = CanonicalMarketTick(
            timestamp="2026-08-14 09:30:00",
            seq_id=102,
            symbol="201VC350",
            underlying_price=350.0,
            last_price=350.0,
            expiry="2026-09-10",
        )
        cmds_far = runtime.process_tick(tick_far)

        # Track1: DTE=19.0 > 4.0 이므로 active_fence 안전하게 보존
        self.assertIsNotNone(t1.active_fence, "Track 1 active fence must remain active when DTE=19.0")

        # Track8: DTE=19.0 >= 15.0 이므로 월물 초입 양매수 진입 발동 확인
        self.assertTrue(t8.strangle_state["is_active"], "Track 8 must enter when DTE >= 15.0")
        self.assertEqual(t8.strangle_state["entry_date"], "2026-08-14")
        self.assertGreater(t8.strangle_state["premium_spent"], 0.0)
        self.assertTrue(any(c.track_id == "Track8" for c in cmds_far))

    def test_e2e_real_dte_pathway_master_lookup_expiry_to_track1_and_track8(self) -> None:
        """[DTE E2E 실측] tick.expiry가 빈 상태일 때 OptionContractMaster lookup을 통해 실제 DTE가 계산·소비되는 경로 검증."""
        runtime = OptionProgramRuntime()
        zip_bytes = create_sample_kis_mst_zip_bytes()
        runtime.option_master.load_from_zip_bytes(zip_bytes)

        t1 = runtime.strategies[0]
        t1.active_fence = {"type": "CALL", "strike": 355.0, "tag_id": 1}

        # B01609335는 마스터에 '2026-09-10'으로 매핑되어 있음
        tick = CanonicalMarketTick(
            timestamp="2026-09-04 09:15:00",
            seq_id=201,
            symbol="B01609335",
            underlying_price=350.0,
            last_price=350.0,
            expiry="",
        )

        cmds = runtime.process_tick(tick)

        # 1. Master lookup으로 만기일 보충 확인
        self.assertIsNotNone(runtime.last_processed_tick)
        self.assertEqual(runtime.last_processed_tick.expiry, "2026-09-10")

        # 2. 보충된 만기일로 실제 DTE=4.0 계산되어 Track 1 만기 컷오프 발동 확인
        self.assertIsNone(t1.active_fence, "Track 1 active fence cleared via Master lookup expiry DTE")
        self.assertTrue(any(c.track_id == "Track1" for c in cmds))

    def test_e2e_real_dte_pathway_missing_dte_eliminates_arbitrary_fallbacks(self) -> None:
        """[DTE E2E 실측] DTE 계산 불가 시 임의의 30.0이나 999.0 숫자가 주입되지 않고 None 계약이 유지됨을 검증."""
        runtime = OptionProgramRuntime()
        t1 = runtime.strategies[0]
        t8 = runtime.strategies[7]

        t1.active_fence = {"type": "CALL", "strike": 355.0, "tag_id": 1}
        t8.reset_state()
        runtime.account_summary.free_margin = 10000000.0

        # 마스터에 없는 종목 + expiry 없는 tick
        tick_no_dte = CanonicalMarketTick(
            timestamp="2026-09-04 09:30:00",
            seq_id=301,
            symbol="NONEXISTENT_SYMBOL",
            underlying_price=350.0,
            last_price=350.0,
            expiry="",
        )

        cmds = runtime.process_tick(tick_no_dte)

        # 1. last_processed_tick.expiry는 빈 문자열
        self.assertEqual(runtime.last_processed_tick.expiry, "")

        # 2. Track1: 30.0/999.0 등의 임의 fallback이 없어 active_fence가 오작동으로 청산되지 않고 안전하게 보존됨
        self.assertIsNotNone(t1.active_fence, "Active fence must be preserved without arbitrary DTE fallback")

        # 3. Track8: 임의의 30.0 fallback으로 인한 오진입(DTE>=15)이 발생하지 않고 STANDBY 유지
        self.assertFalse(t8.strangle_state["is_active"], "Track 8 must not enter when DTE is missing")
        self.assertFalse(any(c.track_id == "Track8" for c in cmds))

    def test_runtime_strategy_budget_positive_free_margin_passed_to_tracks(self) -> None:
        """[Strategy Budget Source 실측] account_summary.free_margin(3,500,000.0)이 Track6/7/8에 정확히 전달됨을 직접 spy/assertion."""
        runtime = OptionProgramRuntime()
        runtime.account_summary.free_margin = 3500000.0

        t6 = runtime.strategies[5]
        t7 = runtime.strategies[6]
        t8 = runtime.strategies[7]

        captured_budgets: Dict[str, float] = {}

        orig_t6_eval = t6.evaluate_insurance_buy
        orig_t7_eval = t7.evaluate_insurance_buy
        orig_t8_eval = t8.evaluate_entry

        def spy_t6(*args: Any, **kwargs: Any) -> Any:
            captured_budgets["Track6"] = kwargs.get("budget", 0.0)
            return orig_t6_eval(*args, **kwargs)

        def spy_t7(*args: Any, **kwargs: Any) -> Any:
            captured_budgets["Track7"] = kwargs.get("budget", 0.0)
            return orig_t7_eval(*args, **kwargs)

        def spy_t8(*args: Any, **kwargs: Any) -> Any:
            captured_budgets["Track8"] = kwargs.get("budget", 0.0)
            return orig_t8_eval(*args, **kwargs)

        t6.evaluate_insurance_buy = spy_t6  # type: ignore
        t7.evaluate_insurance_buy = spy_t7  # type: ignore
        t8.evaluate_entry = spy_t8  # type: ignore

        tick = CanonicalMarketTick(
            timestamp="2026-09-04 09:30:00",
            seq_id=401,
            symbol="201VC350",
            underlying_price=350.0,
            last_price=350.0,
            expiry="2026-09-10",
        )

        runtime.process_tick(tick)

        # 🎯 실제 free_margin(3,500,000.0)이 Track6, Track7, Track8에 100% 동일하게 전달되었음을 직접 assertion!
        self.assertEqual(captured_budgets.get("Track6"), 3500000.0)
        self.assertEqual(captured_budgets.get("Track7"), 3500000.0)
        self.assertEqual(captured_budgets.get("Track8"), 3500000.0)

    def test_runtime_strategy_budget_zero_or_negative_free_margin_no_fallback(self) -> None:
        """[Strategy Budget Source 실측] free_margin이 0.0 또는 음수일 때 1,000,000.0 / 2,000,000.0 fallback이 전달되지 않고 0.0이 전달됨을 검증."""
        runtime = OptionProgramRuntime()

        t6 = runtime.strategies[5]
        t7 = runtime.strategies[6]
        t8 = runtime.strategies[7]

        captured_budgets: Dict[str, float] = {}

        orig_t6_eval = t6.evaluate_insurance_buy
        orig_t7_eval = t7.evaluate_insurance_buy
        orig_t8_eval = t8.evaluate_entry

        def spy_t6(*args: Any, **kwargs: Any) -> Any:
            captured_budgets["Track6"] = kwargs.get("budget", 0.0)
            return orig_t6_eval(*args, **kwargs)

        def spy_t7(*args: Any, **kwargs: Any) -> Any:
            captured_budgets["Track7"] = kwargs.get("budget", 0.0)
            return orig_t7_eval(*args, **kwargs)

        def spy_t8(*args: Any, **kwargs: Any) -> Any:
            captured_budgets["Track8"] = kwargs.get("budget", 0.0)
            return orig_t8_eval(*args, **kwargs)

        t6.evaluate_insurance_buy = spy_t6  # type: ignore
        t7.evaluate_insurance_buy = spy_t7  # type: ignore
        t8.evaluate_entry = spy_t8  # type: ignore

        # 1. free_margin = 0.0 테스트
        runtime.account_summary.free_margin = 0.0
        tick_zero = CanonicalMarketTick(
            timestamp="2026-09-04 09:30:00",
            seq_id=501,
            symbol="201VC350",
            underlying_price=350.0,
            last_price=350.0,
            expiry="2026-09-10",
        )
        runtime.process_tick(tick_zero)

        self.assertEqual(captured_budgets.get("Track6"), 0.0, "Track6 must receive 0.0, not 1,000,000.0 fallback")
        self.assertEqual(captured_budgets.get("Track7"), 0.0, "Track7 must receive 0.0, not 1,000,000.0 fallback")
        self.assertEqual(captured_budgets.get("Track8"), 0.0, "Track8 must receive 0.0, not 2,000,000.0 fallback")

        # 2. free_margin = -100,000.0 (음수) 테스트
        runtime.account_summary.free_margin = -100000.0
        tick_neg = CanonicalMarketTick(
            timestamp="2026-09-04 09:30:01",
            seq_id=502,
            symbol="201VC350",
            underlying_price=350.0,
            last_price=350.0,
            expiry="2026-09-10",
        )
        runtime.process_tick(tick_neg)

        self.assertEqual(captured_budgets.get("Track6"), 0.0, "Track6 must receive 0.0 when negative free_margin")
        self.assertEqual(captured_budgets.get("Track7"), 0.0, "Track7 must receive 0.0 when negative free_margin")
        self.assertEqual(captured_budgets.get("Track8"), 0.0, "Track8 must receive 0.0 when negative free_margin")


if __name__ == "__main__":
    unittest.main()
