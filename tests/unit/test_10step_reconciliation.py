"""Unit test for 10-Step Execution & Reconciliation Pipeline."""
from verify_10step_reconciliation import verify_10step_reconciliation_pipeline
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime
from shared.contracts.canonical import CanonicalOrderCommand, CanonicalOrderSide, CanonicalAssetType, CanonicalMarketTick

def test_10step_reconciliation_healthy_pass() -> None:
    """[Audit] Verify 10-Step Execution Pipeline Reconciliation Auditor returns 100% Healthy."""
    is_healthy = verify_10step_reconciliation_pipeline()
    assert is_healthy is True

def test_vssf_runtime_run_reconciliation_direct() -> None:
    """[Audit] Direct VSSF runtime reconciliation audit check."""
    vssf = VirtualSecuritiesFirmRuntime(initial_capital=25000000.0)
    tick = CanonicalMarketTick(timestamp="2026-08-23 09:00:00", underlying_price=350.0, last_price=350.0)
    vssf.process_market_data(tick)
    
    cmd = CanonicalOrderCommand(
        client_order_id="ORD-REC-001",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=1,
        price=2.50
    )
    vssf.process_order(cmd)
    rec = vssf.run_reconciliation()
    
    assert rec["is_healthy"] is True
    assert rec["balance_ok"] is True
    assert rec["margin_ok"] is True
    assert rec["balance_diff"] < 1e-2
    assert rec["margin_diff"] < 1e-2
