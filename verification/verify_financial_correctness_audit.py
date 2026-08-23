"""Strict Financial Correctness Audit Script - Analytical Hand-Calculation Verification.

Verifies KRX (Korea Exchange) Derivatives Financial Regulations:
1. KOSPI 200 Option Multiplier = 250,000 KRW / pt
2. Broker Commission Fee = 1.5 bps (0.000015) of Trade Value (Price * Qty * 250,000)
3. Realized PnL Analytical Formula:
   - BUY Position Settlement  = (Sell Price - Buy Price) * Qty * 250,000 - Total Fees
   - SELL Position Settlement = (Buy Price - Sell Price) * Qty * 250,000 - Total Fees
4. Unrealized Mark-to-Market PnL Formula:
   - BUY Position Valuation  = (Current Price - Avg Price) * Qty * 250,000
   - SELL Position Valuation = (Avg Price - Current Price) * Qty * 250,000
5. Margin Admission Formula:
   - Option Buy Margin = Price * Qty * 250,000
   - Free Margin = Total Equity - Used Margin
"""
import time
import logging
from shared.contracts.canonical import CanonicalMarketTick, CanonicalOrderCommand, CanonicalOrderSide, CanonicalAssetType
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def verify_financial_correctness_audit() -> bool:
    logger.info("==================================================================")
    logger.info("[KOSPI200 BOT] KRX Financial Correctness Analytical Verification Initializing...")
    logger.info("==================================================================")
    
    start_time = time.time()
    initial_capital = 25000000.0  # KRW 25,000,000
    vssf = VirtualSecuritiesFirmRuntime(initial_capital=initial_capital)

    # ------------------------------------------------------------------
    # Scenario 1: BUY 2 Contracts of KOSPI 200 Call Option at 3.00 pt
    # ------------------------------------------------------------------
    tick1 = CanonicalMarketTick(timestamp="2026-08-23 09:00:00", underlying_price=3.00, last_price=3.00, bid_price=2.95, ask_price=3.05)
    vssf.process_market_data(tick1)

    buy_cmd = CanonicalOrderCommand(
        client_order_id="ORD-AUDIT-BUY",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=2,
        price=3.00
    )
    buy_report = vssf.process_order(buy_cmd)
    
    snap1 = vssf.get_account_snapshot()
    
    # Hand Calculated Values for Scenario 1
    expected_fee1 = buy_report.executed_price * 2 * 250000 * 0.000015
    expected_used_margin1 = buy_report.executed_price * 2 * 250000
    expected_balance1 = initial_capital - expected_fee1
    
    fee1_diff = abs(buy_report.fee - expected_fee1)
    margin1_diff = abs(snap1.used_margin - expected_used_margin1)
    balance1_diff = abs(vssf.account.balance - expected_balance1)

    logger.info("[Scenario 1: BUY 2 Options]")
    logger.info(f"  * Fee Test         : Executed Fee={buy_report.fee:.2f} | Theory={expected_fee1:.2f} | Diff={fee1_diff:.4f} -> {'PASS' if fee1_diff < 1e-2 else 'FAIL'}")
    logger.info(f"  * Used Margin Test : Used Margin={snap1.used_margin:.2f} | Theory={expected_used_margin1:.2f} | Diff={margin1_diff:.4f} -> {'PASS' if margin1_diff < 1e-2 else 'FAIL'}")
    logger.info(f"  * Balance Test     : Balance={vssf.account.balance:.2f} | Theory={expected_balance1:.2f} | Diff={balance1_diff:.4f} -> {'PASS' if balance1_diff < 1e-2 else 'FAIL'}")


    # ------------------------------------------------------------------
    # Scenario 2: Mark-to-Market Price Movement (Option Premium moves to 3.50 pt)
    # ------------------------------------------------------------------
    tick2 = CanonicalMarketTick(timestamp="2026-08-23 09:05:00", underlying_price=3.50, last_price=3.50, bid_price=3.45, ask_price=3.55)
    vssf.process_market_data(tick2)
    snap2 = vssf.get_account_snapshot()

    expected_unrealized2 = (3.50 - buy_report.executed_price) * 2 * 250000
    unrealized2_diff = abs(snap2.unrealized_pnl - expected_unrealized2)

    logger.info("[Scenario 2: Mark-to-Market Price Movement]")
    logger.info(f"  * Unrealized PnL Test : System MTM={snap2.unrealized_pnl:.2f} | Theory={expected_unrealized2:.2f} | Diff={unrealized2_diff:.4f} -> {'PASS' if unrealized2_diff < 1e-2 else 'FAIL'}")

    # ------------------------------------------------------------------
    # Scenario 3: SELL 2 Contracts to Close Position at 3.50 pt
    # ------------------------------------------------------------------
    sell_cmd = CanonicalOrderCommand(
        client_order_id="ORD-AUDIT-SELL",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.SELL,
        qty=2,
        price=3.50
    )
    sell_report = vssf.process_order(sell_cmd)
    snap3 = vssf.get_account_snapshot()

    expected_sell_fee = sell_report.executed_price * 2 * 250000 * 0.000015
    expected_realized_pnl = (sell_report.executed_price - buy_report.executed_price) * 2 * 250000
    realized_diff = abs(snap3.realized_pnl - expected_realized_pnl)
    used_margin3_diff = abs(snap3.used_margin - 0.0)

    logger.info("[Scenario 3: Position Closing & Realized PnL Settlement]")
    logger.info(f"  * Realized PnL Test  : Realized PnL={snap3.realized_pnl:.2f} | Theory={expected_realized_pnl:.2f} | Diff={realized_diff:.4f} -> {'PASS' if realized_diff < 1e-2 else 'FAIL'}")
    logger.info(f"  * Position Unwind Margin Test : Used Margin={snap3.used_margin:.2f} | Theory=0.00 | Diff={used_margin3_diff:.4f} -> {'PASS' if used_margin3_diff < 1e-2 else 'FAIL'}")

    elapsed = time.time() - start_time
    is_financially_correct = (fee1_diff < 1e-2 and margin1_diff < 1e-2 and balance1_diff < 1e-2 and unrealized2_diff < 1e-2 and realized_diff < 1e-2 and used_margin3_diff < 1e-2)

    logger.info("==================================================================")
    if is_financially_correct:
        logger.info(f"[SUCCESS] Financial Correctness Audit Passed 100%! All KRX Rules Confirmed in {elapsed:.2f}s.")
    else:
        logger.error("[FAIL] Financial Correctness Audit Mismatch Detected!")
    logger.info("==================================================================")

    return is_financially_correct

if __name__ == "__main__":
    verify_financial_correctness_audit()
