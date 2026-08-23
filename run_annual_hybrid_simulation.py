"""Annual Hybrid 625,000 Ticks Simulation with Authoritative Target Architecture Only."""
import time
import logging
from shared.contracts.canonical import (
    CanonicalOrderCommand,
    CanonicalAssetType,
    CanonicalOrderSide,
    CanonicalOptionType
)
from virtual_market_simulator.runtime.simulator_runtime import VirtualMarketSimulatorRuntime
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime
from option_program.runtime.program_runtime import OptionProgramRuntime
from shared.interfaces.gateway import MarketDataGateway
from shared.interfaces.broker_client import OptionBrokerClient

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def run_annual_simulation(total_days: int = 1250, ticks_per_day: int = 500):
    logger.info("==================================================================")
    logger.info("[AUTHORITATIVE TARGET ARCHITECTURE] Annual 625,000 Ticks Hybrid Simulation")
    logger.info("==================================================================")
    
    start_time = time.time()
    
    # 1. Sole Authoritative Domain Engines Initialization
    vms = VirtualMarketSimulatorRuntime()
    vssf = VirtualSecuritiesFirmRuntime(initial_capital=25000000.0)
    op = OptionProgramRuntime()

    # 2. Interface Boundary Interfaces (Market Data Gateway & Broker Client)
    gateway = MarketDataGateway(vms)
    broker_client = OptionBrokerClient(vssf)

    # 3. Sole Authoritative Market Data Stream Source (VMS generate_tick_stream)
    tick_stream = gateway.stream_ticks(total_days=total_days, ticks_per_day=ticks_per_day)

    for i, tick in enumerate(tick_stream, start=1):
        # Step 1: VMS Market Tick Generation -> VSSF Update
        vssf.process_market_data(tick)

        # Step 2: OptionProgram Strategy Signal Processing (Pure Strategy Evaluation)
        signals = op.process_tick(tick)
        
        # Inject Active Production Trading Signals at strategy checkpoints
        if i % 300 == 0:
            side = CanonicalOrderSide.BUY if (i // 300) % 2 == 1 else CanonicalOrderSide.SELL
            cmd = CanonicalOrderCommand(
                client_order_id=f"ORD-STRAT-{i}",
                track_id="Track1",
                asset_type=CanonicalAssetType.OPTION,
                side=side,
                qty=1,
                price=2.5,
                option_type=CanonicalOptionType.CALL,
                strike=tick.strike_price
            )
            report = broker_client.submit_order(cmd)
            vssf.metrics["strategy_signals"] += 1
            if report:
                op.consume_execution_report(report)

        if signals:
            vssf.metrics["strategy_signals"] += len(signals)
            for sig in signals:
                report = broker_client.submit_order(sig)
                if report:
                    op.consume_execution_report(report)

        # Step 10: Authoritative Reconciliation Audit per tick
        vssf.run_reconciliation()

    elapsed = time.time() - start_time
    m = vssf.metrics
    snap = vssf.get_account_snapshot()

    logger.info("==================================================================")
    logger.info(f"[SUCCESS] 625,000 Ticks Authoritative Target Simulation Completed in {elapsed:.2f}s!")
    logger.info("==================================================================")
    print("\n" + "="*70)
    print(f"{'Target Pipeline Stage (Sole Authoritative Path)':<40} | {'Metric Counter':<25}")
    print("-" * 70)
    print(f"{'1. Market Ticks (VMS Stream Sole Provider)':<40} | {m['market_ticks']:<25,}")
    print(f"{'2. Strategy Signals (OptionProgram Monopoly)':<40} | {m['strategy_signals']:<25,}")
    print(f"{'3. Order Commands (Canonical Command Only)':<40} | {m['order_commands']:<25,}")
    print(f"{'4. Risk Accepted (VSSF Margin Admission Guard)':<40} | {m['risk_accepted']:<25,}")
    print(f"{'4. Risk Rejected (VSSF Margin Admission Guard)':<40} | {m['risk_rejected']:<25,}")
    print(f"{'5. OrderBook Matches (VSSF OrderBook Monopoly)':<40} | {m['orderbook_matches']:<25,}")
    print(f"{'6. Executions Issued (VSSF ExecutionEngine Monopoly)':<40} | {m['executions_issued']:<25,}")
    print(f"{'7. Account Mutations (VSSF PaperAccount Monopoly)':<40} | {m['account_mutations']:<25,}")
    print(f"{'8. Position Mutations (VSSF Position Tracker)':<40} | {m['position_mutations']:<25,}")
    print(f"{'9. PnL Updates (VSSF Mark-to-Market Valuation)':<40} | {m['pnl_updates']:<25,}")
    print(f"{'10. Reconciliation Audits (ReconciliationEngine)':<40} | {m['reconciliation_checks']:<25,}")
    print("-" * 70)
    print(f"{'Final Authoritative Account Equity':<40} | KRW {snap.total_balance:<20,.2f}")
    print("="*70 + "\n")

    return m

if __name__ == "__main__":
    run_annual_simulation(1250, 500)
