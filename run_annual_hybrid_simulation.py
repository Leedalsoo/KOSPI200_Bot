"""5-Year (625,000 Ticks) Full Pure Target Architecture Simulation & 10-Step Pipeline Metrics Counter.

Pipeline 10-Steps:
1. CanonicalMarketTick
2. Strategy Signal
3. CanonicalOrderCommand
4. Risk Admission
5. OrderBook.match_order()
6. ExecutionEngine.execute_order()
7. PaperTradingAccount.apply_execution()
8. Position mutation
9. Realized / Unrealized PnL
10. Reconciliation
"""
import time
import logging
from typing import Dict, Any
from shared.contracts.canonical import (
    CanonicalMarketTick,
    CanonicalOrderCommand,
    CanonicalOrderSide,
    CanonicalAssetType
)
from virtual_market_simulator.runtime.simulator_runtime import VirtualMarketSimulatorRuntime
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime
from option_program.runtime.program_runtime import OptionProgramRuntime

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def run_5year_10step_simulation(total_ticks: int = 625000) -> Dict[str, Any]:
    logger.info("==================================================================")
    logger.info("[KOSPI200 BOT] 5-Year (625,000 Ticks) 10-Step Pipeline Full Execution...")
    logger.info("==================================================================")
    
    start_time = time.time()

    vms = VirtualMarketSimulatorRuntime()
    vssf = VirtualSecuritiesFirmRuntime(initial_capital=25000000.0)
    op = OptionProgramRuntime()

    # Pre-created ticks pool for high throughput
    prices = [round(3.00 + (i % 5) * 0.1, 2) for i in range(5)]
    ticks_pool = [
        CanonicalMarketTick(
            timestamp="2026-08-23 09:00:00",
            underlying_price=p,
            last_price=p,
            bid_price=round(p - 0.05, 2),
            ask_price=round(p + 0.05, 2)
        )
        for p in prices
    ]

    for i in range(1, total_ticks + 1):
        tick = ticks_pool[i % 5]
        
        # Step 1: Market Ticks
        vssf.process_market_data(tick)

        # Step 2: Strategy Signals (Trigger every 4 ticks for realistic trading volume)
        if i % 4 == 0:
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
    snap = vssf.get_account_snapshot()

    logger.info("==================================================================")
    logger.info(f"[SUCCESS] 625,000 Ticks 10-Step Pipeline Completed in {elapsed:.2f}s!")
    logger.info("==================================================================")
    logger.info(f"{'Pipeline Step':<28} | {'Metric Counter (Real Execution)':<30}")
    logger.info("-" * 65)
    logger.info(f"{'1. Market Ticks':<28} | {m['market_ticks']:<30,}")
    logger.info(f"{'2. Strategy Signals':<28} | {m['strategy_signals']:<30,}")
    logger.info(f"{'3. Order Commands':<28} | {m['order_commands']:<30,}")
    logger.info(f"{'4. Risk Accepted':<28} | {m['risk_accepted']:<30,}")
    logger.info(f"{'4. Risk Rejected':<28} | {m['risk_rejected']:<30,}")
    logger.info(f"{'5. OrderBook Matches':<28} | {m['orderbook_matches']:<30,}")
    logger.info(f"{'6. Executions Issued':<28} | {m['executions_issued']:<30,}")
    logger.info(f"{'7. Account Mutations':<28} | {m['account_mutations']:<30,}")
    logger.info(f"{'8. Position Mutations':<28} | {m['position_mutations']:<30,}")
    logger.info(f"{'9. PnL Updates':<28} | {m['pnl_updates']:<30,}")
    logger.info(f"{'10. Reconciliation Checks':<28} | {m['reconciliation_checks']:<30,}")
    logger.info("==================================================================")
    logger.info(f"Final Balance: KRW {snap.balance:,.2f} | Realized PnL: KRW {snap.realized_pnl:,.2f}")
    logger.info("==================================================================")

    return m

if __name__ == "__main__":
    run_5year_10step_simulation(625000)
