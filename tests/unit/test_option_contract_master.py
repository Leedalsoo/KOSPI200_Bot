# -*- coding: utf-8 -*-
"""Unit tests for OptionContractMaster contract and Runtime Expiry Lookup Integration."""
import unittest

from shared.calendar.krx_calendar import KrxTradingCalendar
from shared.contracts.canonical import CanonicalMarketTick
from shared.contracts.option_master import (
    IOptionContractMaster,
    InMemoryOptionContractMaster,
)
from option_program.runtime.program_runtime import OptionProgramRuntime


class TestOptionContractMaster(unittest.TestCase):
    """OptionContractMaster 및 Runtime Expiry Lookup 연동 검증."""

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

    def test_runtime_expiry_lookup_via_symbol(self) -> None:
        """Runtime이 tick.symbol을 통해 OptionContractMaster에서 expiry를 조회하고 DTE를 계산하는지 검증."""
        runtime = OptionProgramRuntime(
            calendar=self.calendar,
            option_master=self.master,
        )

        # Track 1에 가두리 세팅
        t1 = runtime.strategies[0]
        t1.active_fence = {"type": "CALL", "strike": 355.0, "tag_id": 1}

        # 틱 생성: expiry는 비어있지만 symbol="201V8350"이 제공됨 (만기일 2026-09-04)
        # 현재일 2026-08-28(금) 기준 2026-09-04(금)까지 남은 거래일은 3일 (8/31, 9/1 공휴일 가정 시 3일, 일반 주말 시 5일)
        tick_with_symbol = CanonicalMarketTick(
            timestamp="2026-08-28 09:00:01",
            underlying_price=350.0,
            bid_price=349.9,
            ask_price=350.1,
            last_price=350.0,
            volume=10,
            seq_id=1,
            symbol="201V8350",
            expiry="",
        )

        cmds = runtime.process_tick(tick_with_symbol)
        # DTE가 정상 계산되어 5.0일 이하(또는 컷오프)로 전달되어 가두리 청산이 발동되거나 시그널 생성 확인
        self.assertIsNone(t1.active_fence, "Track 1 active fence cleared on DTE <= 4.0 or cutoff")

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


if __name__ == "__main__":
    unittest.main()
