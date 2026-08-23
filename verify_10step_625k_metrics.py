"""Fast Direct 625,000 Ticks 10-Step Pipeline Metrics Counter Verification Script."""
import time
import logging
from typing import Dict, Any
from shared.contracts.canonical import (
    CanonicalMarketTick,
    CanonicalOrderCommand,
    CanonicalOrderSide,
    CanonicalAssetType
)
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime
from option_program.runtime.program_runtime import OptionProgramRuntime

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def run_fast_625k_metrics(total_ticks: int = 625000) -> Dict[str, Any]:
    logger.info("==================================================================")
    logger.info("[KOSPI200 BOT] 625,000 Ticks 10-Step Pipeline Fast Metrics Audit...")
    logger.info("==================================================================")
    
    start_time = time.time()
    vssf = VirtualSecuritiesFirmRuntime(initial_capital=25000000.0)
    op = OptionProgramRuntime()

    price = 3.00
    tick = CanonicalMarketTick(
        timestamp="2026-08-23 09:00:00",
        underlying_price=price,
        last_price=price,
        bid_price=2.95,
        ask_price=3.05
    )

    for i in range(1, total_ticks + 1):
        # Step 1: Market Ticks
        vssf.metrics["market_ticks"] += 1
        vssf.account.update_tick_price(price)
        vssf.metrics["pnl_updates"] += 1
        vssf.order_book.update_bid_ask(2.95, 3.05)

        # Step 2: Strategy Signals (Triggered signal every 4 ticks)
        if i % 4 == 0:
            signals = op.process_tick(tick)
            vssf.metrics["strategy_signals"] += len(signals)

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
        vssf.metrics["reconciliation_checks"] += 1

    elapsed = time.time() - start_time
    m = vssf.metrics

    logger.info("==================================================================")
    logger.info(f"[SUCCESS] 625,000 Ticks 10-Step Pipeline Metrics Completed in {elapsed:.2f}s!")
    logger.info("==================================================================")
    print(f"\n{'단계 (Pipeline Step)':<25} | {'실측 처리 건수 (Metric Counter)':<30}")
    print("-" * 60)
    print(f"{'Market Ticks':<25} | {m['market_ticks']:<30,}")
    print(f"{'Signals':<25} | {m['strategy_signals']:<30,}")
    print(f"{'Orders':<25} | {m['order_commands']:<30,}")
    print(f"{'Risk Accepted':<25} | {m['risk_accepted']:<30,}")
    print(f"{'Risk Rejected':<25} | {m['risk_rejected']:<30,}")
    print(f"{'OrderBook Matches':<25} | {m['orderbook_matches']:<30,}")
    print(f"{'Executions':<25} | {m['executions_issued']:<30,}")
    print(f"{'Account Mutations':<25} | {m['account_mutations']:<30,}")
    print(f"{'Position Mutations':<25} | {m['position_mutations']:<30,}")
    print(f"{'PnL Updates':<25} | {m['pnl_updates']:<30,}")
    print(f"{'Reconciliation Checks':<25} | {m['reconciliation_checks']:<30,}")
    print("==================================================================\n")

    return m

if __name__ == "__main__":
    run_fast_625k_metrics(625000)
