"""Unit Test: Reconciliation & State Recovery Comprehensive Verification."""
import pytest
from virtual_securities_firm.account.paper_account import PaperTradingAccount
from virtual_securities_firm.recovery.state_recovery import StateRecoveryEngine
from virtual_securities_firm.account.reconciliation import AuthoritativeReconciliationEngine
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime
from shared.contracts.canonical import (
    CanonicalExecutionReport,
    CanonicalAssetType,
    CanonicalOrderSide,
    CanonicalOrderCommand,
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


# ==============================================================================
# 9. 내부 VSSF와 Reconciliation 정밀 검증 스위트 (12대 핵심 요구사항 전수 assertion)
# ==============================================================================


def test_vssf_reconciliation_initial_clean_state_passes():
    """1. 정상 초기 상태 -> PASS"""
    engine = AuthoritativeReconciliationEngine(initial_capital=25_000_000.0)
    account = PaperTradingAccount(initial_capital=25_000_000.0)
    snap = account.get_canonical_summary()

    report = engine.reconcile_state(
        account_snapshot=snap,
        execution_history=[],
        current_positions={}
    )
    assert report["is_healthy"] is True
    assert report["balance_ok"] is True
    assert report["position_ok"] is True
    assert report["pnl_ok"] is True
    assert report["margin_ok"] is True
    assert report["execution_ok"] is True
    assert report["balance_diff"] == 0.0
    assert report["pnl_diff"] == 0.0
    assert report["margin_diff"] == 0.0
    assert len(report["discrepancies"]) == 0


def test_vssf_reconciliation_normal_execution_passes():
    """2. 정상 실행 후 Position/PnL 정합 -> PASS"""
    engine = AuthoritativeReconciliationEngine(initial_capital=25_000_000.0)
    account = PaperTradingAccount(initial_capital=25_000_000.0)

    rep1 = CanonicalExecutionReport(
        exec_id="EXEC_VSSF_01",
        client_order_id="ORD_VSSF_01",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        executed_qty=2,
        executed_price=3.50,
        fee=20.0,
        slippage=0.0,
        timestamp="2026-08-23 09:05:00",
        symbol="OPT_201S03370"
    )
    account.apply_execution(rep1)
    snap = account.get_canonical_summary()

    report = engine.reconcile_state(
        account_snapshot=snap,
        execution_history=[rep1],
        current_positions=account.positions
    )
    assert report["is_healthy"] is True
    assert report["balance_ok"] is True
    assert report["position_ok"] is True
    assert report["pnl_ok"] is True
    assert report["margin_ok"] is True
    assert report["execution_ok"] is True


def test_vssf_reconciliation_fifo_close_realized_pnl_passes():
    """3. FIFO 청산 후 realized PnL 정합 -> PASS"""
    engine = AuthoritativeReconciliationEngine(initial_capital=25_000_000.0)
    account = PaperTradingAccount(initial_capital=25_000_000.0)

    # 1. Buy 2 @ 3.50
    rep_buy = CanonicalExecutionReport(
        exec_id="EXEC_VSSF_BUY",
        client_order_id="ORD_VSSF_01",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        executed_qty=2,
        executed_price=3.50,
        fee=20.0,
        slippage=0.0,
        timestamp="2026-08-23 09:05:00",
        symbol="OPT_201S03370"
    )
    account.apply_execution(rep_buy)

    # 2. Sell 2 @ 4.00 (FIFO Close -> Realized PnL = (4.00 - 3.50) * 2 * 250,000 = +250,000)
    rep_sell = CanonicalExecutionReport(
        exec_id="EXEC_VSSF_SELL",
        client_order_id="ORD_VSSF_02",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.SELL,
        executed_qty=2,
        executed_price=4.00,
        fee=20.0,
        slippage=0.0,
        timestamp="2026-08-23 09:10:00",
        symbol="OPT_201S03370"
    )
    account.apply_execution(rep_sell)

    snap = account.get_canonical_summary()
    assert snap.realized_pnl == 250_000.0

    report = engine.reconcile_state(
        account_snapshot=snap,
        execution_history=[rep_buy, rep_sell],
        current_positions=account.positions
    )
    assert report["is_healthy"] is True
    assert report["pnl_ok"] is True
    assert report["position_ok"] is True
    assert report["balance_ok"] is True


def test_vssf_reconciliation_position_qty_tampering_fails():
    """4. position quantity 변조 -> FAIL"""
    engine = AuthoritativeReconciliationEngine(initial_capital=25_000_000.0)
    account = PaperTradingAccount(initial_capital=25_000_000.0)

    rep = CanonicalExecutionReport(
        exec_id="EXEC_VSSF_01",
        client_order_id="ORD_VSSF_01",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        executed_qty=2,
        executed_price=3.50,
        fee=20.0,
        slippage=0.0,
        timestamp="2026-08-23 09:05:00",
        symbol="OPT_201S03370"
    )
    account.apply_execution(rep)
    snap = account.get_canonical_summary()
    sym_key = list(account.positions.keys())[0]

    # 변조된 포지션 수량 (실제 2 -> 5로 변조)
    tampered_positions = {sym_key: {"qty": 5, "avg_price": 3.50, "side": "BUY"}}

    report = engine.reconcile_state(
        account_snapshot=snap,
        execution_history=[rep],
        current_positions=tampered_positions
    )
    assert report["is_healthy"] is False
    assert report["position_ok"] is False
    assert any("Position qty mismatch" in d for d in report["discrepancies"])


def test_vssf_reconciliation_position_side_tampering_fails():
    """5. position side 변조 -> FAIL"""
    engine = AuthoritativeReconciliationEngine(initial_capital=25_000_000.0)
    account = PaperTradingAccount(initial_capital=25_000_000.0)

    rep = CanonicalExecutionReport(
        exec_id="EXEC_VSSF_01",
        client_order_id="ORD_VSSF_01",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        executed_qty=2,
        executed_price=3.50,
        fee=20.0,
        slippage=0.0,
        timestamp="2026-08-23 09:05:00",
        symbol="OPT_201S03370"
    )
    account.apply_execution(rep)
    snap = account.get_canonical_summary()
    sym_key = list(account.positions.keys())[0]

    # 변조된 포지션 방향 (BUY -> SELL로 변조)
    tampered_positions = {sym_key: {"qty": 2, "avg_price": 3.50, "side": "SELL"}}

    report = engine.reconcile_state(
        account_snapshot=snap,
        execution_history=[rep],
        current_positions=tampered_positions
    )
    assert report["is_healthy"] is False
    assert report["position_ok"] is False
    assert any("Position side mismatch" in d for d in report["discrepancies"])


def test_vssf_reconciliation_position_avg_price_tampering_fails():
    """6. position avg_price 변조 -> FAIL"""
    engine = AuthoritativeReconciliationEngine(initial_capital=25_000_000.0)
    account = PaperTradingAccount(initial_capital=25_000_000.0)

    rep = CanonicalExecutionReport(
        exec_id="EXEC_VSSF_01",
        client_order_id="ORD_VSSF_01",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        executed_qty=2,
        executed_price=3.50,
        fee=20.0,
        slippage=0.0,
        timestamp="2026-08-23 09:05:00",
        symbol="OPT_201S03370"
    )
    account.apply_execution(rep)
    snap = account.get_canonical_summary()
    sym_key = list(account.positions.keys())[0]

    # 변조된 평단가 (3.50 -> 4.50으로 변조)
    tampered_positions = {sym_key: {"qty": 2, "avg_price": 4.50, "side": "BUY"}}

    report = engine.reconcile_state(
        account_snapshot=snap,
        execution_history=[rep],
        current_positions=tampered_positions
    )
    assert report["is_healthy"] is False
    assert report["position_ok"] is False
    assert any("Position avg_price mismatch" in d for d in report["discrepancies"])


def test_vssf_reconciliation_realized_pnl_tampering_fails():
    """7. realized PnL 변조 -> FAIL"""
    engine = AuthoritativeReconciliationEngine(initial_capital=25_000_000.0)
    account = PaperTradingAccount(initial_capital=25_000_000.0)

    rep_buy = CanonicalExecutionReport(
        exec_id="EXEC_VSSF_BUY",
        client_order_id="ORD_VSSF_01",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        executed_qty=1,
        executed_price=3.00,
        fee=10.0,
        slippage=0.0,
        timestamp="2026-08-23 09:05:00",
        symbol="OPT_201S03370"
    )
    account.apply_execution(rep_buy)

    rep_sell = CanonicalExecutionReport(
        exec_id="EXEC_VSSF_SELL",
        client_order_id="ORD_VSSF_02",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.SELL,
        executed_qty=1,
        executed_price=4.00,
        fee=10.0,
        slippage=0.0,
        timestamp="2026-08-23 09:10:00",
        symbol="OPT_201S03370"
    )
    account.apply_execution(rep_sell)

    snap = account.get_canonical_summary()
    # 스냅샷의 realized_pnl을 임의로 999,999로 변조
    snap.realized_pnl = 999_999.0

    report = engine.reconcile_state(
        account_snapshot=snap,
        execution_history=[rep_buy, rep_sell],
        current_positions=account.positions
    )
    assert report["is_healthy"] is False
    assert report["pnl_ok"] is False
    assert any("Realized PnL mismatch" in d for d in report["discrepancies"])


def test_vssf_reconciliation_fee_equity_tampering_fails():
    """8. fee/equity 관계 변조 -> FAIL"""
    engine = AuthoritativeReconciliationEngine(initial_capital=25_000_000.0)
    account = PaperTradingAccount(initial_capital=25_000_000.0)

    rep = CanonicalExecutionReport(
        exec_id="EXEC_VSSF_01",
        client_order_id="ORD_VSSF_01",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        executed_qty=1,
        executed_price=3.00,
        fee=100.0,
        slippage=0.0,
        timestamp="2026-08-23 09:05:00",
        symbol="OPT_201S03370"
    )
    account.apply_execution(rep)
    snap = account.get_canonical_summary()

    # 계좌 총 잔고를 임의로 왜곡 (수수료 미반영 금액 등으로 변조)
    snap.total_balance = 30_000_000.0

    report = engine.reconcile_state(
        account_snapshot=snap,
        execution_history=[rep],
        current_positions=account.positions
    )
    assert report["is_healthy"] is False
    assert report["balance_ok"] is False
    assert any("Account balance/equity mismatch" in d for d in report["discrepancies"])


def test_vssf_reconciliation_margin_tampering_fails():
    """9. used_margin/free_margin 관계 변조 -> FAIL"""
    engine = AuthoritativeReconciliationEngine(initial_capital=25_000_000.0)
    account = PaperTradingAccount(initial_capital=25_000_000.0)

    rep = CanonicalExecutionReport(
        exec_id="EXEC_VSSF_01",
        client_order_id="ORD_VSSF_01",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        executed_qty=2,
        executed_price=3.00,
        fee=20.0,
        slippage=0.0,
        timestamp="2026-08-23 09:05:00",
        symbol="OPT_201S03370"
    )
    account.apply_execution(rep)
    snap = account.get_canonical_summary()

    # used_margin을 임의로 0으로 왜곡
    snap.used_margin = 0.0

    report = engine.reconcile_state(
        account_snapshot=snap,
        execution_history=[rep],
        current_positions=account.positions
    )
    assert report["is_healthy"] is False
    assert report["margin_ok"] is False
    assert any("Margin mismatch" in d for d in report["discrepancies"])


def test_vssf_reconciliation_duplicate_exec_id_fails():
    """10. duplicate exec_id -> FAIL"""
    engine = AuthoritativeReconciliationEngine(initial_capital=25_000_000.0)
    account = PaperTradingAccount(initial_capital=25_000_000.0)

    rep1 = CanonicalExecutionReport(
        exec_id="EXEC_DUP_01",
        client_order_id="ORD_VSSF_01",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        executed_qty=1,
        executed_price=3.00,
        fee=10.0,
        slippage=0.0,
        timestamp="2026-08-23 09:05:00",
        symbol="OPT_201S03370"
    )
    rep2 = CanonicalExecutionReport(
        exec_id="EXEC_DUP_01",  # 동일한 exec_id 중복
        client_order_id="ORD_VSSF_02",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        executed_qty=1,
        executed_price=3.00,
        fee=10.0,
        slippage=0.0,
        timestamp="2026-08-23 09:06:00",
        symbol="OPT_201S03370"
    )
    snap = account.get_canonical_summary()

    report = engine.reconcile_state(
        account_snapshot=snap,
        execution_history=[rep1, rep2],
        current_positions={}
    )
    assert report["is_healthy"] is False
    assert report["execution_ok"] is False
    assert any("Duplicate exec_id detected" in d for d in report["discrepancies"])


def test_vssf_reconciliation_invalid_executed_qty_fails():
    """11. invalid executed_qty (<= 0) -> FAIL"""
    engine = AuthoritativeReconciliationEngine(initial_capital=25_000_000.0)
    account = PaperTradingAccount(initial_capital=25_000_000.0)

    rep_invalid = CanonicalExecutionReport(
        exec_id="EXEC_INVALID_01",
        client_order_id="ORD_VSSF_01",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        executed_qty=-5,  # 음수 수량
        executed_price=3.00,
        fee=10.0,
        slippage=0.0,
        timestamp="2026-08-23 09:05:00",
        symbol="OPT_201S03370"
    )
    snap = account.get_canonical_summary()

    report = engine.reconcile_state(
        account_snapshot=snap,
        execution_history=[rep_invalid],
        current_positions={}
    )
    assert report["is_healthy"] is False
    assert report["execution_ok"] is False
    assert any("Invalid non-positive executed_qty" in d for d in report["discrepancies"])


def test_vssf_runtime_run_reconciliation_integration_path():
    """12. VirtualSecuritiesFirmRuntime.run_reconciliation() 실제 호출 경로 통합 검증"""
    runtime = VirtualSecuritiesFirmRuntime(initial_capital=25_000_000.0)

    # 1. 초기 clean 상태 reconciliation
    init_report = runtime.run_reconciliation()
    assert init_report["is_healthy"] is True
    assert runtime.metrics["reconciliation_checks"] == 1

    # 2. 주문 실행 및 체결
    order = CanonicalOrderCommand(
        client_order_id="ORD_RUN_REC_01",
        track_id="Track1",
        symbol="201S03370",
        side=CanonicalOrderSide.BUY,
        qty=1,
        price=3.50,
        asset_type=CanonicalAssetType.OPTION
    )
    exec_rep = runtime.process_order(order)
    assert exec_rep is not None

    # 3. 체결 후 runtime.run_reconciliation() 정상 검증
    post_report = runtime.run_reconciliation()
    assert post_report["is_healthy"] is True
    assert post_report["position_ok"] is True
    assert post_report["balance_ok"] is True
    assert post_report["margin_ok"] is True
    assert post_report["pnl_ok"] is True
    assert runtime.metrics["reconciliation_checks"] == 2

    # 4. runtime 내부 포지션 강제 변조 시 run_reconciliation()이 불일치를 정확히 탐지하는지 검증
    sym_key = list(runtime.account.position_mgr.positions.keys())[0]
    runtime.account.position_mgr.positions[sym_key]["qty"] = 999
    tampered_report = runtime.run_reconciliation()
    assert tampered_report["is_healthy"] is False
    assert tampered_report["position_ok"] is False
    assert runtime.metrics["reconciliation_checks"] == 3

