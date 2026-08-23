"""Target Architecture Integration Integration Test."""
import pytest
from virtual_market_simulator.runtime.simulator_runtime import VirtualMarketSimulatorRuntime
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime
from option_program.runtime.program_runtime import OptionProgramRuntime
from shared.contracts.canonical import CanonicalOrderCommand
from datetime import datetime

def test_target_architecture_full_integration():
    vms = VirtualMarketSimulatorRuntime(time_scale=1.0)
    vsf = VirtualSecuritiesFirmRuntime()
    op = OptionProgramRuntime(vsf, vms)
    
    tick = vms.next_tick()
    assert tick["status"] == "ACTIVE"
    assert tick["underlying_price"] == 360.0
    
    order = CanonicalOrderCommand(
        order_id="ORD-001",
        symbol="KOSPI200_OPT",
        side="BUY",
        order_type="LIMIT",
        price=3.5,
        quantity=2,
        created_at=datetime.now()
    )
    
    report = vsf.submit_order(order)
    assert report.order_id == "ORD-001"
    assert report.quantity == 2
    assert report.price == 3.5
    
    acct = vsf.get_account_summary()
    assert acct.total_balance == 100000000.0
