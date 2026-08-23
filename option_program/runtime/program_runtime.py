"""Option Program Runtime Entrypoint."""
from typing import Dict, Any, Optional
from shared.contracts.canonical import CanonicalOrderCommand, CanonicalExecutionReport
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime
from virtual_market_simulator.runtime.simulator_runtime import VirtualMarketSimulatorRuntime

class OptionProgramRuntime:
    def __init__(self, vsf_runtime: VirtualSecuritiesFirmRuntime, vms_runtime: VirtualMarketSimulatorRuntime):
        self.vsf = vsf_runtime
        self.vms = vms_runtime
        self.active = True

    def process_tick(self) -> Optional[CanonicalExecutionReport]:
        tick = self.vms.next_tick()
        price = tick.get("underlying_price", 360.0)
        return None
