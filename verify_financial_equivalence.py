"""Financial Equivalence Strict Verification Script.

Compares financial calculation metrics between:
1. Legacy direct calculation model
2. Target Architecture Authoritative Owner model (VMS -> VSSF -> OptionProgram -> VSSF Matching)

Verifies 8 Core Financial Metrics:
- Total Balance / Equity
- Realized PnL
- Unrealized PnL
- Used Margin
- Free Margin
- Total Executed Quantity
- Total Commission Fees
- Total Slippage
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
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime
from virtual_securities_firm.account.paper_account import PaperTradingAccount
from virtual_securities_firm.execution.execution_engine import SlippageEngine

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def run_legacy_baseline(ticks_count: int = 50) -> Dict[str, float]:
    """[Legacy Baseline Calculation Model]"""
    account = PaperTradingAccount(initial_capital=25000000.0)
    slippage_engine = SlippageEngine()
    
    total_fee = 0.0
    total_slippage = 0.0
    total_qty = 0

    for i in range(1, ticks_count + 1):
        price = 350.0 + (i % 5) * 0.1
        account.update_tick_price(price)
        
        if i % 2 == 0:
            side = "BUY" if (i // 2) % 2 == 1 else "SELL"
            # Broker margin check
            est_cost = 2.50 * 1 * 250000
            if side == "BUY" and account.canonical_summary.free_margin < est_cost:
                continue

            slip_res = slippage_engine.calculate_execution("LIMIT", side, 2.50, 1)
            exec_price = float(slip_res.get("executed_price", 2.50))
            slip = float(slip_res.get("slippage", 0.0))
            fee = exec_price * 1 * 250000 * 0.000015
            
            account.apply_execution(
                track_id="Track1",
                side=side,
                qty=1,
                price=exec_price,
                fee=fee
            )
            total_fee += fee
            total_slippage += slip
            total_qty += 1

    summary = account.canonical_summary
    return {
        "balance": round(summary.total_balance, 2),
        "realized_pnl": round(summary.realized_pnl, 2),
        "unrealized_pnl": round(summary.unrealized_pnl, 2),
        "used_margin": round(summary.used_margin, 2),
        "free_margin": round(summary.free_margin, 2),
        "total_qty": float(total_qty),
        "total_fee": round(total_fee, 2),
        "total_slippage": round(total_slippage, 4)
    }

def run_target_architecture_model(ticks_count: int = 50) -> Dict[str, float]:
    """[Target Architecture Authoritative Owner Model]"""
    vssf = VirtualSecuritiesFirmRuntime(initial_capital=25000000.0)
    
    total_fee = 0.0
    total_slippage = 0.0
    total_qty = 0

    for i in range(1, ticks_count + 1):
        price = 350.0 + (i % 5) * 0.1
        tick = CanonicalMarketTick(timestamp="2026-08-23 09:00:00", underlying_price=price, last_price=price)
        vssf.process_market_data(tick)
        
        if i % 2 == 0:
            side = CanonicalOrderSide.BUY if (i // 2) % 2 == 1 else CanonicalOrderSide.SELL
            cmd = CanonicalOrderCommand(
                client_order_id=f"ORD-EQUIV-{i}",
                track_id="Track1",
                asset_type=CanonicalAssetType.OPTION,
                side=side,
                qty=1,
                price=2.50
            )
            report = vssf.process_order(cmd)
            if report:
                total_fee += report.fee
                total_slippage += report.slippage
                total_qty += report.executed_qty

    snap = vssf.get_account_snapshot()
    return {
        "balance": round(snap.balance, 2),
        "realized_pnl": round(snap.realized_pnl, 2),
        "unrealized_pnl": round(snap.unrealized_pnl, 2),
        "used_margin": round(snap.used_margin, 2),
        "free_margin": round(snap.free_margin, 2),
        "total_qty": float(total_qty),
        "total_fee": round(total_fee, 2),
        "total_slippage": round(total_slippage, 4)
    }

def verify_financial_equivalence():
    logger.info("==================================================================")
    logger.info("[KOSPI200 BOT] Financial Equivalence Strict Verification Initializing...")
    logger.info("==================================================================")
    
    ticks_count = 100
    start_time = time.time()
    
    legacy_res = run_legacy_baseline(ticks_count)
    target_res = run_target_architecture_model(ticks_count)
    elapsed = time.time() - start_time

    diffs = {}
    passed = True
    
    logger.info(f"{'Metric Name':<20} | {'Legacy Value':<18} | {'Target Value':<18} | {'Diff':<10} | Status")
    logger.info("-" * 80)

    for key in legacy_res:
        leg_val = legacy_res[key]
        tgt_val = target_res[key]
        diff = abs(leg_val - tgt_val)
        diffs[key] = diff
        
        status = "MATCH (100.0%)" if diff < 1e-4 else "MISMATCH"
        if diff >= 1e-4:
            passed = False
        logger.info(f"{key:<20} | {leg_val:<18,.2f} | {tgt_val:<18,.2f} | {diff:<10.4f} | {status}")

    logger.info("==================================================================")
    if passed:
        logger.info(f"[SUCCESS] Financial Equivalence Verified 100% Match! (0.00% Diff across all 8 metrics, Time: {elapsed:.2f}s)")
    else:
        logger.error("[FAIL] Financial Equivalence Mismatch Detected!")
    logger.info("==================================================================")
    
    return passed, diffs

if __name__ == "__main__":
    verify_financial_equivalence()
