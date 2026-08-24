"""Unit Test: VSSF (Virtual Securities Simulation Framework) Authoritative Architecture Comprehensive Verification."""
import pytest
from virtual_securities_firm.account.paper_account import PaperTradingAccount
from virtual_securities_firm.execution.execution_engine import ExecutionEngine
from virtual_securities_firm.settlement.settlement_engine import SettlementEngine
from shared.contracts.canonical import (
    CanonicalOrderCommand,
    CanonicalExecutionReport,
    CanonicalAssetType,
    CanonicalOrderSide
)

def test_vssf_single_source_of_truth_isolation():
    """Validates that PaperTradingAccount delegates state mutations exclusively to VSSF sub-domain engines."""
    account = PaperTradingAccount(initial_capital=50_000_000.0)
    assert account.balance == 50_000_000.0
    assert len(account.positions) == 0

    # Execute trade via ExecutionEngine
    exec_engine = ExecutionEngine()
    cmd = CanonicalOrderCommand(
        client_order_id="ORD_VSSF_01",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=2,
        price=2.00
    )
    report = exec_engine.execute_order(cmd, fill_price=2.00, fill_qty=2)

    # Apply execution to Account
    account.apply_execution(report)

    # Verify positions and ledger recorded
    assert "KOSPI200_OPTION" in account.positions or getattr(report, "symbol", None) in account.positions or len(account.positions) == 1
    assert len(account.ledger_engine.transactions) == 1
    assert account.ledger_engine.transactions[0]["order_id"] == "ORD_VSSF_01"

def test_vssf_7_domain_engines_coordination():
    """Validates end-to-end coordination of all 7 domain engines in VSSF."""
    account = PaperTradingAccount(initial_capital=50_000_000.0)
    exec_engine = ExecutionEngine()
    settlement_engine = SettlementEngine(account)

    # 1. Buy Order
    cmd_buy = CanonicalOrderCommand(
        client_order_id="ORD_BUY_01",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=4,
        price=2.00
    )
    rep_buy = exec_engine.execute_order(cmd_buy, fill_price=2.00, fill_qty=4)
    account.apply_execution(rep_buy)

    # 2. Price Update (MTM & Margin)
    total_eq = account.update_tick_price(underlying_price=350.0)
    assert total_eq is not None
    assert account.used_margin >= 0.0
    assert account.free_margin >= 0.0

    # 3. Partial Sell Order
    cmd_sell = CanonicalOrderCommand(
        client_order_id="ORD_SELL_01",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.SELL,
        qty=2,
        price=2.50
    )
    rep_sell = exec_engine.execute_order(cmd_sell, fill_price=2.50, fill_qty=2)
    account.apply_execution(rep_sell)

    # Realized PnL should be positive
    assert account.realized_pnl > 0.0

    # 4. EOD Settlement
    record = settlement_engine.perform_eod_settlement(final_settlement_price=350.0)
    assert record["type"] == "EOD"
    assert len(account.ledger_engine.transactions) >= 3

def test_vssf_accounting_identity_invariants():
    """Validates accounting invariant: Total Equity == Balance + Realized PnL + Unrealized PnL."""
    account = PaperTradingAccount(initial_capital=30_000_000.0)
    exec_engine = ExecutionEngine()

    cmd = CanonicalOrderCommand(
        client_order_id="ORD_INV_01",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=2,
        price=1.50
    )
    rep = exec_engine.execute_order(cmd, fill_price=1.50, fill_qty=2)
    account.apply_execution(rep)
    account.update_tick_price(underlying_price=348.0)

    summary = account.get_canonical_summary()
    expected_balance = round(account.balance + account.realized_pnl + account.unrealized_pnl, 2)
    assert summary.total_balance == expected_balance

def test_vssf_margin_diet_guard_trigger():
    """Validates margin engine margin ratio calculation and diet guard behavior."""
    account = PaperTradingAccount(initial_capital=10_000_000.0)
    # Simulate high used margin
    account.position_mgr.positions["FUT_SHORT"] = {"qty": 10, "avg_price": 350.0, "side": "SELL"}
    account.used_margin = account.margin_engine.calculate_used_margin(account.position_mgr.positions)
    assert account.used_margin > 0.0
    account.update_tick_price(underlying_price=360.0)
    # With extreme loss and high used margin, free margin is 0.0
    assert account.free_margin == 0.0

def test_vssf_settlement_ledger_audit_trail():
    """Validates settlement and execution double-entry audit trail."""
    account = PaperTradingAccount(initial_capital=40_000_000.0)
    settlement_engine = SettlementEngine(account)

    # Record Expiry Settlement
    account.positions["201V350_CALL"] = {"qty": 2, "avg_price": 1.50, "side": "BUY"}
    cash = settlement_engine.perform_expiry_settlement("201V350_CALL", final_index_price=352.0)
    assert cash == 1_000_000.0

    ledger_entries = account.ledger_engine.get_ledger_records()
    expiry_entries = [e for e in ledger_entries if "EXPIRY" in str(e.get("settlement_type", ""))]
    assert len(expiry_entries) == 1
    assert expiry_entries[0]["realized_pnl"] == 1_000_000.0
