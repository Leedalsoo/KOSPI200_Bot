"""Strict 10-Step Execution & Reconciliation Pipeline Verification Script.

10-Step Architecture Pipeline:
1. Market (VMS Market Tick)
2. Signal (OptionProgram Signal Evaluation)
3. Order (CanonicalOrderCommand)
4. Risk (Broker Margin Admission)
5. OrderBook (Real-time Bids/Asks Matching)
6. Execution (Slippage & Fee Computation)
7. Account (Asset & Ledger Mutation)
8. Position (Position Tracking)
9. PnL (Realized & Unrealized PnL Engine)
10. Reconciliation (State Integrity Auditing)
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

def verify_10step_reconciliation_pipeline() -> bool:
    logger.info("==================================================================")
    logger.info("[KOSPI200 BOT] 10-Step Pipeline & Reconciliation Audit Verification Initializing...")
    logger.info("==================================================================")
    
    start_time = time.time()
    
    # 1. Component Runtime Initialization
    vms = VirtualMarketSimulatorRuntime()
    vssf = VirtualSecuritiesFirmRuntime(initial_capital=25000000.0)
    op = OptionProgramRuntime()

    total_ticks = 100
    executions_count = 0

    for i in range(1, total_ticks + 1):
        # Step 1: Market
        raw_tick = vms.step()
        price = float(raw_tick.get("price", 350.0))
        tick = CanonicalMarketTick(
            timestamp="2026-08-23 09:00:00",
            underlying_price=price,
            last_price=price,
            bid_price=round(price - 0.05, 2),
            ask_price=round(price + 0.05, 2)
        )
        vssf.process_market_data(tick)

        # Step 2: Signal Evaluation
        signals = op.process_tick(tick)

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
                executions_count += 1
                op.consume_execution_report(report)

    # Step 10: Reconciliation Auditing
    rec_report = vssf.run_reconciliation()
    elapsed = time.time() - start_time

    logger.info("-" * 80)
    logger.info(f"10-Step Pipeline Run Completed in {elapsed:.2f}s across {total_ticks} Ticks | Executions: {executions_count}")
    logger.info(f"  * Balance Integrity Audit  : {'PASS' if rec_report['balance_ok'] else 'FAIL'} (Diff: {rec_report['balance_diff']})")
    logger.info(f"  * Margin Risk Audit        : {'PASS' if rec_report['margin_ok'] else 'FAIL'} (Diff: {rec_report['margin_diff']})")
    logger.info(f"  * Position Integrity Audit : {'PASS' if rec_report['position_ok'] else 'FAIL'}")
    logger.info(f"  * Realized/Unrealized PnL : {'PASS' if rec_report['pnl_ok'] else 'FAIL'}")
    logger.info(f"  * Overall Reconciliation    : {'HEALTHY (100% PASS)' if rec_report['is_healthy'] else 'UNHEALTHY'}")
    logger.info("==================================================================")

    return rec_report["is_healthy"]

if __name__ == "__main__":
    verify_10step_reconciliation_pipeline()
