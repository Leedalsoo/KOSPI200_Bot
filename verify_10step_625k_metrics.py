"""Fast 625,000 Ticks 10-Step Pipeline Metrics Verification with Authoritative VMS Market Stream."""
import time
import logging
from typing import Dict, Any
from shared.contracts.canonical import CanonicalOrderCommand
from virtual_market_simulator.runtime.simulator_runtime import VirtualMarketSimulatorRuntime
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime
from option_program.runtime.program_runtime import OptionProgramRuntime

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def run_vms_625k_metrics(total_ticks: int = 625000) -> Dict[str, Any]:
    logger.info("==================================================================")
    logger.info("[KOSPI200 BOT] 625,000 Ticks VMS Stream 10-Step Pipeline Metrics Audit...")
    logger.info("==================================================================")
    
    start_time = time.time()
    
    # Real VMS Runtime Single Source of Truth Market Stream Provider
    vms = VirtualMarketSimulatorRuntime()
    vssf = VirtualSecuritiesFirmRuntime(initial_capital=25000000.0)
    op = OptionProgramRuntime()

    tick_stream = vms.generate_tick_stream(total_days=1250, ticks_per_day=500)

    for i, tick in enumerate(tick_stream, start=1):
        # Step 1: Market Ticks from VMS Real Stream
        vssf.process_market_data(tick)

        # Step 2: Strategy Signals (Triggered from VMS Market Tick for EVERY Tick)
        signals = op.process_tick(tick)
        vssf.metrics["strategy_signals"] += len(signals)

        # Step 3~9: Order -> Risk -> OrderBook -> Execution -> Account -> Position -> PnL
        for sig in signals:
            cmd = CanonicalOrderCommand(
                client_order_id=sig.client_order_id,
                track_id=sig.track_id,
                asset_type=sig.asset_type,
                side=sig.side,
                qty=sig.qty,
                price=sig.price
            )
            report = vssf.process_order(cmd)
            if report:
                op.consume_execution_report(report)

        # Step 10: Reconciliation Auditing (per tick)
        vssf.run_reconciliation()

    elapsed = time.time() - start_time
    m = vssf.metrics

    logger.info("==================================================================")
    logger.info(f"[SUCCESS] 625,000 VMS Ticks 10-Step Pipeline Completed in {elapsed:.2f}s!")
    logger.info("==================================================================")
    print(f"\n{'단계 (Pipeline Step)':<30} | {'실측 처리 건수 (Metric Counter)':<30}")
    print("-" * 65)
    print(f"{'1. Market Ticks (VMS Stream)':<30} | {m['market_ticks']:<30,}")
    print(f"{'2. Strategy Signals':<30} | {m['strategy_signals']:<30,}")
    print(f"{'3. Order Commands':<30} | {m['order_commands']:<30,}")
    print(f"{'4. Risk Accepted':<30} | {m['risk_accepted']:<30,}")
    print(f"{'4. Risk Rejected':<30} | {m['risk_rejected']:<30,}")
    print(f"{'5. OrderBook Matches':<30} | {m['orderbook_matches']:<30,}")
    print(f"{'6. Executions':<30} | {m['executions_issued']:<30,}")
    print(f"{'7. Account Mutations':<30} | {m['account_mutations']:<30,}")
    print(f"{'8. Position Mutations':<30} | {m['position_mutations']:<30,}")
    print(f"{'9. PnL Updates':<30} | {m['pnl_updates']:<30,}")
    print(f"{'10. Reconciliation Checks':<30} | {m['reconciliation_checks']:<30,}")
    print("==================================================================\n")

    return m

if __name__ == "__main__":
    run_vms_625k_metrics(625000)
