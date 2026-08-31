# -*- coding: utf-8 -*-
import pytest
from shared.contracts.canonical import (
    CanonicalAssetType,
    CanonicalOptionType,
    CanonicalOrderCommand,
    CanonicalOrderSide,
)
from option_program.broker.broker_interface import PaperBrokerAdapter
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime


def test_chaos_monkey_fault_injection_latency() -> None:
    """[카오스 검증] 카오스 지연 주입 하에서 지연 동작이 정상 수행되는지 확인"""
    vssf = VirtualSecuritiesFirmRuntime(initial_capital=50_000_000.0)
    adapter = PaperBrokerAdapter(vssf_runtime=vssf)
    adapter.set_latency(50.0)
    adapter.set_execution_behavior("DELAYED")

    cmd = CanonicalOrderCommand(
        client_order_id="ORD-CHAOS-001",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=1,
        price=3.50,
        option_type=CanonicalOptionType.CALL,
        strike=350.0,
        symbol="KOSPI200"
    )
    report = adapter.send_order(cmd)
    assert report is not None
    assert report.client_order_id == "ORD-CHAOS-001"


def test_chaos_monkey_fault_injection_disconnect() -> None:
    """[카오스 검증] 카오스 연결 단절 시 주문이 차단되는지 확인"""
    vssf = VirtualSecuritiesFirmRuntime(initial_capital=50_000_000.0)
    adapter = PaperBrokerAdapter(vssf_runtime=vssf)
    adapter.set_connection(False)

    cmd = CanonicalOrderCommand(
        client_order_id="ORD-CHAOS-002",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=1,
        price=3.50,
        option_type=CanonicalOptionType.CALL,
        strike=350.0,
        symbol="KOSPI200"
    )
    report = adapter.send_order(cmd)
    assert report.success is False
    assert report.status == "DISCONNECTED"


