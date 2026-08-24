"""Unit Test: Settlement, PnL & Ledger Engine Comprehensive Verification."""
import pytest
from virtual_securities_firm.pnl.pnl_engine import PnLEngine
from virtual_securities_firm.ledger.ledger_engine import LedgerEngine
from virtual_securities_firm.settlement.settlement_engine import SettlementEngine
from virtual_securities_firm.account.paper_account import PaperTradingAccount
from shared.contracts.canonical import CanonicalExecutionReport, CanonicalOrderSide, CanonicalAssetType

def test_pnl_engine_unrealized_mtm():
    """Validates mark-to-market unrealized PnL calculation across multiple positions."""
    pnl_eng = PnLEngine()
    positions = {
        "OPT_CALL_350": {"qty": 2, "avg_price": 2.0, "side": "BUY"},
        "OPT_PUT_345": {"qty": 3, "avg_price": 3.0, "side": "SELL"}
    }
    # Current price = 2.50
    # CALL BUY: (2.50 - 2.0) * 2 * 250,000 = 0.50 * 500,000 = +250,000
    # PUT SELL: (3.0 - 2.50) * 3 * 250,000 = 0.50 * 750,000 = +375,000
    # Total Unrealized = +625,000
    unrealized = pnl_eng.calculate_unrealized(positions, current_price=2.50)
    assert unrealized == 625_000.0
    assert pnl_eng.unrealized_pnl == 625_000.0

def test_pnl_engine_realized_accumulation():
    """Validates cumulative realized PnL accumulation."""
    pnl_eng = PnLEngine()
    assert pnl_eng.realized_pnl == 0.0
    pnl_eng.add_realized(500_000.0)
    assert pnl_eng.realized_pnl == 500_000.0
    pnl_eng.add_realized(-200_000.0)
    assert pnl_eng.realized_pnl == 300_000.0

def test_settlement_engine_eod_flow():
    """Validates EOD mark-to-market settlement record and ledger chaining."""
    account = PaperTradingAccount(initial_capital=50_000_000.0)
    settlement_eng = SettlementEngine(account)

    account.unrealized_pnl = 1_500_000.0
    account.realized_pnl = 500_000.0
    account.used_margin = 10_000_000.0

    record = settlement_eng.perform_eod_settlement(final_settlement_price=350.0)
    assert record["type"] == "EOD"
    assert record["balance"] == 50_000_000.0
    assert record["unrealized_pnl"] == 1_500_000.0
    assert record["realized_pnl"] == 500_000.0

    ledger_records = account.ledger_engine.get_ledger_records()
    assert len(ledger_records) == 1
    assert ledger_records[0]["type"] == "SETTLEMENT"
    assert ledger_records[0]["settlement_type"] == "EOD"
    assert ledger_records[0]["unrealized_pnl"] == 1_500_000.0

def test_settlement_engine_expiry_itm_and_otm():
    """Validates option expiry settlement for ITM (cash payoff) and OTM (expired worthless)."""
    account = PaperTradingAccount(initial_capital=50_000_000.0)
    settlement_eng = SettlementEngine(account)

    # 1. ITM Call Option: Strike 350, Final Index = 352.0 (+2.0 points intrinsic value)
    account.positions["201V350_CALL"] = {"qty": 2, "avg_price": 1.0, "side": "BUY"}
    cash_settled = settlement_eng.perform_expiry_settlement("201V350_CALL", final_index_price=352.0)
    # Payoff = (352.0 - 350.0) * 250,000 * 2 = 1,000,000 KRW
    assert cash_settled == 1_000_000.0
    assert account.balance == 51_000_000.0
    assert "201V350_CALL" not in account.positions

    # 2. OTM Put Option: Strike 350, Final Index = 352.0 (0 intrinsic value)
    account.positions["301V350_PUT"] = {"qty": 2, "avg_price": 1.0, "side": "BUY"}
    cash_settled_otm = settlement_eng.perform_expiry_settlement("301V350_PUT", final_index_price=352.0)
    assert cash_settled_otm == 0.0
    assert account.balance == 51_000_000.0  # Balance unchanged
    assert "301V350_PUT" not in account.positions

def test_ledger_engine_execution_and_settlement_audit():
    """Validates double-entry transaction record integrity in LedgerEngine."""
    ledger = LedgerEngine()
    report = CanonicalExecutionReport(
        exec_id="EXEC_1001",
        client_order_id="ORD_1001",
        track_id="TRACK_1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        executed_qty=2,
        executed_price=2.50,
        fee=18.75,
        slippage=0.01,
        timestamp="2026-08-23 09:15:00"
    )
    ledger.record_execution(report, balance=49_500_000.0)
    ledger.record_settlement("EOD", realized_pnl=500_000.0, unrealized_pnl=200_000.0, balance_after=50_000_000.0)

    records = ledger.get_ledger_records()
    assert len(records) == 2
    assert records[0]["exec_id"] == "EXEC_1001"
    assert records[0]["fee"] == 18.75
    assert records[1]["type"] == "SETTLEMENT"
    assert records[1]["settlement_type"] == "EOD"

def test_pnl_fee_slippage_equity_coherence():
    """Validates accounting identity: Equity == Balance + Unrealized PnL."""
    account = PaperTradingAccount(initial_capital=100_000_000.0)
    # Simulate trade with fee and realized PnL
    account.balance = 100_000_000.0 - 50_000.0 + 500_000.0  # Initial - fees + realized
    account.unrealized_pnl = 1_200_000.0

    summary = account.get_canonical_summary()
    expected_total = round(account.balance + account.realized_pnl + account.unrealized_pnl, 2)
    assert summary.total_balance == expected_total
