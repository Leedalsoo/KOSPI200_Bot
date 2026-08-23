"""Target Architecture Integration Integration Test."""
import pytest
from virtual_market_simulator.runtime.simulator_runtime import VirtualMarketSimulatorRuntime
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime
from option_program.runtime.program_runtime import OptionProgramRuntime
from shared.contracts.canonical import (
    CanonicalOrderCommand,
    CanonicalAssetType,
    CanonicalOrderSide
)
from datetime import datetime

def test_target_architecture_full_integration():
    vms = VirtualMarketSimulatorRuntime()
    vsf = VirtualSecuritiesFirmRuntime()
    op = OptionProgramRuntime()
    
    tick = vms.step()
    assert tick is not None
    assert "price" in tick
    
    order = CanonicalOrderCommand(
        client_order_id="ORD-001",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=2,
        price=3.5
    )
    
    report = vsf.process_order(order)
    assert report is not None
    assert report.client_order_id == "ORD-001"
    assert report.executed_qty == 2
    assert report.executed_price > 0
    
    acct = vsf.get_account_snapshot()
    assert acct.balance == 25000000.0
