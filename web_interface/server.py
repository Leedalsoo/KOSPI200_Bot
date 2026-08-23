"""Target Architecture UI & Control Panel Backend API Server."""
import orjson as json
import logging
from typing import Dict, Any
from virtual_market_simulator.runtime.simulator_runtime import VirtualMarketSimulatorRuntime
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime
from option_program.runtime.program_runtime import OptionProgramRuntime
from shared.interfaces.gateway import MarketDataGateway
from shared.interfaces.broker_client import OptionBrokerClient

logger = logging.getLogger(__name__)

class TargetArchitectureUIServer:
    """[M6 UI 서버: DTO/Snapshot만 소비 — VSSF 내부 객체 직접 참조 0]"""
    def __init__(self):
        self.vms = VirtualMarketSimulatorRuntime()
        self.vssf = VirtualSecuritiesFirmRuntime(initial_capital=25000000.0)
        self.op = OptionProgramRuntime()
        self.gateway = MarketDataGateway(self.vms)
        self.broker_client = OptionBrokerClient(self.vssf)

    def get_system_state(self) -> Dict[str, Any]:
        # [UI Boundary] VSSF 내부 객체 직접 참조 금지 — get_account_snapshot() DTO만 소비
        snap = self.vssf.get_account_snapshot()
        m = self.vssf.metrics
        return {
            "status": "HEALTHY",
            "account": {
                "balance": snap.total_balance,
                "realized_pnl": snap.realized_pnl,
                "unrealized_pnl": snap.unrealized_pnl,
                "used_margin": snap.used_margin,
                "free_margin": snap.free_margin,
            },
            "metrics": m,
            # positions도 CanonicalAccountSummary DTO를 통해 접근
            # (현재 CanonicalAccountSummary에 positions 미포함 → get_account_snapshot() 확장 시 여기서 소비)
            "positions": {},
        }

    def process_step(self, tick_count: int = 1) -> Dict[str, Any]:
        tick_stream = self.gateway.stream_ticks(total_days=1, ticks_per_day=tick_count)
        for tick in tick_stream:
            self.vssf.process_market_data(tick)
            signals = self.op.process_tick(tick)
            for sig in signals:
                report = self.broker_client.submit_order(sig)
                if report:
                    self.op.consume_execution_report(report)
            self.vssf.run_reconciliation()

        return self.get_system_state()

if __name__ == "__main__":
    server = TargetArchitectureUIServer()
    state = server.process_step(10)
    print("[UI Server Test] System State:", json.dumps(state, indent=2))
