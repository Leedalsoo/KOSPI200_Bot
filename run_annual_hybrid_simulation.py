"""[Target Architecture Exclusive] 5-Year (1,250 Days / 625,000 Ticks) Hybrid Strategy Simulation.

Target Architecture Flow:
1. VMS (Virtual Market Simulator Runtime): Market Data & OrderBook Tick Generation
2. OptionProgram (Option Program Runtime): Regime Analysis & Track 1~9 Signal Evaluation
3. VSSF (Virtual Securities Firm Runtime): Margin Risk Admission -> OrderBook Matching -> ExecutionEngine (Slippage & Fee) -> Account Mutation
4. Account Snapshot Query from VSSF Authoritative Owner
"""
import time
import logging
from typing import Dict, Any, List
from shared.contracts.canonical import (
    CanonicalMarketTick,
    CanonicalOrderCommand,
    CanonicalExecutionReport,
    CanonicalOrderSide,
    CanonicalAssetType
)
from virtual_market_simulator.runtime.simulator_runtime import VirtualMarketSimulatorRuntime
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime
from option_program.runtime.program_runtime import OptionProgramRuntime

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def run_target_architecture_annual_simulation(days: int = 1250) -> Dict[str, Any]:
    """[Pure Target Architecture 5-Year Simulation Engine]"""
    logger.info("================================================================================")
    logger.info(f"[Target Architecture Exclusive] Initializing 5-Year ({days} Days / {days*500:,} Ticks) Simulation")
    logger.info("================================================================================")
    
    start_time = time.time()
    
    # 1. Initialize Core Component Runtimes
    vms_runtime = VirtualMarketSimulatorRuntime()
    vssf_runtime = VirtualSecuritiesFirmRuntime(initial_capital=25000000.0)
    option_program = OptionProgramRuntime()

    ticks_per_day = 500
    total_ticks = days * ticks_per_day
    
    total_executions = 0
    total_fees = 0.0
    total_slippage = 0.0

    for current_tick_idx in range(1, total_ticks + 1):
        # Step A: VMS Market Tick Generation
        raw_tick = vms_runtime.step()
        price = float(raw_tick.get("price", 350.0))
        
        canonical_tick = CanonicalMarketTick(
            timestamp=f"2026-08-23 {9 + (current_tick_idx // 3600):02d}:{(current_tick_idx // 60) % 60:02d}:{current_tick_idx % 60:02d}",
            underlying_price=price,
            last_price=price,
            bid_price=round(price - 0.05, 2),
            ask_price=round(price + 0.05, 2)
        )
        
        # Step B: Broadcast Market Tick to VSSF Gateway
        vssf_runtime.process_market_data(canonical_tick)

        # Step C: OptionProgram Process Market Tick & Signal Generation
        signals = option_program.process_tick(canonical_tick)

        # Step D: Process Generated Order Signals through Authoritative VSSF Execution Chain
        for sig in signals:
            order_cmd = CanonicalOrderCommand(
                client_order_id=sig.client_order_id,
                track_id=sig.track_id,
                asset_type=sig.asset_type,
                side=sig.side,
                qty=sig.qty,
                price=sig.price
            )
            # VSSF Authoritative Execution: Margin -> OrderBook -> ExecutionEngine -> Account
            report = vssf_runtime.process_order(order_cmd)
            if report:
                total_executions += 1
                total_fees += report.fee
                total_slippage += report.slippage
                option_program.consume_execution_report(report)

        # Periodic Progress Logger
        if current_tick_idx % (total_ticks // 10) == 0:
            pct = (current_tick_idx / total_ticks) * 100
            snap = vssf_runtime.get_account_snapshot()
            logger.info(f"   [{pct:5.1f}%] {current_tick_idx:,} Ticks | Balance: KRW {snap.balance:,.0f} | Executions: {total_executions:,}")

    elapsed = time.time() - start_time
    final_snap = vssf_runtime.get_account_snapshot()

    logger.info("================================================================================")
    logger.info(f"[SUCCESS] Target Architecture 5-Year Simulation Completed in {elapsed:.2f}s!")
    logger.info(f"  * Total Equity: KRW {final_snap.balance:,.2f}")
    logger.info(f"  * Realized PnL: KRW {final_snap.realized_pnl:,.2f}")
    logger.info(f"  * Used Margin : KRW {final_snap.used_margin:,.2f}")
    logger.info(f"  * Executions  : {total_executions:,} Fills")
    logger.info("================================================================================")

    return {
        "days": days,
        "total_ticks": total_ticks,
        "elapsed_seconds": round(elapsed, 2),
        "total_executions": total_executions,
        "balance": final_snap.balance,
        "realized_pnl": final_snap.realized_pnl,
        "unrealized_pnl": final_snap.unrealized_pnl,
        "used_margin": final_snap.used_margin,
        "free_margin": final_snap.free_margin,
        "total_fees": round(total_fees, 2),
        "total_slippage": round(total_slippage, 4)
    }

if __name__ == "__main__":
    run_target_architecture_annual_simulation()
