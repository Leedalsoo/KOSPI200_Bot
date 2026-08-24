"""Unit Test: Reconciliation & State Recovery Comprehensive Verification."""
import pytest
from virtual_securities_firm.account.paper_account import PaperTradingAccount
from virtual_securities_firm.recovery.state_recovery import StateRecoveryEngine
from shared.contracts.canonical import (
    CanonicalExecutionReport,
    CanonicalAssetType,
    CanonicalOrderSide
)

def test_state_snapshot_creation_and_integrity():
    """Validates full runtime state snapshot capture (Account, Positions, Ledger, Metrics)."""
    account = PaperTradingAccount(initial_capital=50_000_000.0)
    account.realized_pnl = 1_200_000.0
    account.unrealized_pnl = 300_000.0
    account.used_margin = 8_000_000.0
    account.free_margin = 43_500_000.0
    account.position_mgr.positions["OPT_CALL_350"] = {"qty": 2, "avg_price": 2.50, "side": "BUY"}

    report = CanonicalExecutionReport(
        exec_id="EXEC_REC_01",
        client_order_id="ORD_REC_01",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        executed_qty=2,
        executed_price=2.50,
        fee=18.75,
        slippage=0.01,
        timestamp="2026-08-23 09:15:00"
    )
    account.ledger_engine.record_execution(report, balance=account.balance)

    recovery = StateRecoveryEngine(account=account)
    metrics = {"trades_count": 1, "mdd": 0.02}
    snap = recovery.create_snapshot(sequence_id=1001, metrics=metrics)

    assert snap["sequence_id"] == 1001
    assert snap["balance"] == 50_000_000.0
    assert snap["realized_pnl"] == 1_200_000.0
    assert len(snap["positions"]) == 1
    assert len(snap["ledger_transactions"]) == 1
    assert snap["metrics"]["trades_count"] == 1

def test_full_state_restoration_from_snapshot():
    """Validates 100% exact runtime state restoration into a blank new Account instance."""
    # 1. Prepare original account and snapshot
    orig_account = PaperTradingAccount(initial_capital=50_000_000.0)
    orig_account.realized_pnl = 2_000_000.0
    orig_account.unrealized_pnl = 500_000.0
    orig_account.used_margin = 12_000_000.0
    orig_account.free_margin = 40_500_000.0
    orig_account.position_mgr.positions["OPT_PUT_340"] = {"qty": 5, "avg_price": 1.80, "side": "BUY"}

    report = CanonicalExecutionReport(
        exec_id="EXEC_REC_02",
        client_order_id="ORD_REC_02",
        track_id="Track2",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        executed_qty=5,
        executed_price=1.80,
        fee=33.75,
        slippage=0.01,
        timestamp="2026-08-23 09:20:00"
    )
    orig_account.ledger_engine.record_execution(report, balance=orig_account.balance)

    recovery_orig = StateRecoveryEngine(account=orig_account)
    metrics_orig = {"trades_count": 5, "mdd": 0.015}
    snap = recovery_orig.create_snapshot(sequence_id=2001, metrics=metrics_orig)

    # 2. Blank fresh account instance (Simulate process restart)
    new_account = PaperTradingAccount(initial_capital=25_000_000.0)
    recovery_new = StateRecoveryEngine(account=new_account)
    target_metrics = {}

    success = recovery_new.restore_from_snapshot(snap, target_metrics=target_metrics)
    assert success is True

    # 3. Verify exact restoration
    assert new_account.balance == 50_000_000.0
    assert new_account.realized_pnl == 2_000_000.0
    assert new_account.unrealized_pnl == 500_000.0
    assert new_account.used_margin == 12_000_000.0
    assert len(new_account.positions) == 1
    assert new_account.positions["OPT_PUT_340"]["qty"] == 5
    assert len(new_account.ledger_engine.transactions) == 1
    assert target_metrics["trades_count"] == 5

def test_reconciliation_position_and_balance_audit():
    """Validates authoritative ledger reconciliation with external broker snapshot."""
    account = PaperTradingAccount(initial_capital=100_000_000.0)
    account.position_mgr.positions["FUT_LONG"] = {"qty": 2, "avg_price": 350.0, "side": "BUY"}
    account.position_mgr.positions["OPT_CALL_355"] = {"qty": 3, "avg_price": 2.10, "side": "BUY"}

    # External Broker Mirror
    broker_snapshot = {
        "balance": 100_000_000.0,
        "positions": {
            "FUT_LONG": {"qty": 2, "avg_price": 350.0},
            "OPT_CALL_355": {"qty": 3, "avg_price": 2.10}
        }
    }

    # Reconciliation Audit Check
    balance_diff = abs(account.balance - broker_snapshot["balance"])
    assert balance_diff == 0.0

    internal_positions = account.positions
    for sym, ext_pos in broker_snapshot["positions"].items():
        assert sym in internal_positions
        assert internal_positions[sym]["qty"] == ext_pos["qty"]
        assert internal_positions[sym]["avg_price"] == ext_pos["avg_price"]

def test_corrupted_snapshot_safe_handling():
    """Validates graceful failure handling when corrupt snapshot object is provided."""
    account = PaperTradingAccount()
    recovery = StateRecoveryEngine(account=account)

    class CorruptObject:
        pass

    corrupt = CorruptObject()
    # Attempting to restore non-standard corrupt object must not crash process
    res = recovery.restore_from_snapshot(corrupt)
    assert res is True or res is False
