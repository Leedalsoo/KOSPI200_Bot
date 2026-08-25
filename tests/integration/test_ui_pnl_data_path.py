from types import SimpleNamespace

from web_interface.server import TargetArchitectureUIServer


def test_ui_snapshot_contains_realtime_pnl_coord():
    tick = SimpleNamespace(
        timestamp="2026-08-25 09:00:01",
        seq_id=42,
        underlying_price=350.0,
        bid_price=349.9,
        ask_price=350.1,
        volume=100,
    )
    account = SimpleNamespace(
        total_balance=50_000_000.0,
        realized_pnl=125_000.0,
        unrealized_pnl=-25_000.0,
        used_margin=1_000_000.0,
        free_margin=49_000_000.0,
        positions={},
    )
    condition = SimpleNamespace(to_dict=lambda: {"regime": "NORMAL"})
    runtime = SimpleNamespace(
        market_condition=condition,
        last_risk_snapshot=None,
        received_execution_reports=[],
        strategy_metrics={},
        current_regime="NORMAL",
        enabled_strategies={},
        last_orders=[],
    )
    system = SimpleNamespace(
        last_tick=tick,
        op_runtime=runtime,
        vssf=SimpleNamespace(get_account_snapshot=lambda: account),
        broker_mode="PAPER",
        ticks_processed=42,
        orders_routed=0,
        executions_handled=0,
    )

    snapshot = TargetArchitectureUIServer(system).snapshot()

    assert snapshot["coord"] == {"x": 42, "y": 100_000.0}
    assert snapshot["pnl"]["total"] == 100_000.0
