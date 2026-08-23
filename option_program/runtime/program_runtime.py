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

    def process_tick(self, tick: Optional[Dict[str, Any]] = None) -> Optional[CanonicalExecutionReport]:
        tick_data = tick if tick is not None else self.vms.next_tick()
        price = tick_data.get("underlying_price", tick_data.get("price", 360.0))
        return None
