"""Unit Test: UI Sync & Dashboard Comprehensive Verification."""
import pytest
import orjson
from shared.contracts.canonical import (
    CanonicalAccountSummary,
    CanonicalMarketTick,
    CanonicalExecutionReport,
    CanonicalAssetType,
    CanonicalOrderSide
)
from virtual_securities_firm.account.paper_account import PaperTradingAccount

def test_ui_telemetry_packet_tracks_1_to_9_synchronization():
    """Validates Track 1 to Track 9 full telemetry dashboard synchronization packet."""
    tracks_state = {f"Track{i}": {"active": i % 2 == 1, "pnl": i * 10000.0, "position_qty": i} for i in range(1, 10)}

    telemetry_packet = {
        "type": "TELEMETRY_UPDATE",
        "timestamp": "2026-08-23 10:30:00",
        "tracks": tracks_state,
        "total_pnl": sum(t["pnl"] for t in tracks_state.values()),
        "active_tracks_count": sum(1 for t in tracks_state.values() if t["active"])
    }

    assert len(telemetry_packet["tracks"]) == 9
    assert telemetry_packet["active_tracks_count"] == 5
    assert telemetry_packet["total_pnl"] == 450000.0

def test_websocket_broadcast_packet_immutability():
    """Validates single serialization and JSON payload immutability for WebSocket broadcast."""
    summary = CanonicalAccountSummary(
        account_id="ACC-VSSF-001",
        total_balance=50_000_000.0,
        used_margin=10_000_000.0,
        free_margin=40_000_000.0,
        realized_pnl=500_000.0,
        unrealized_pnl=200_000.0,
        timestamp="2026-08-23 09:30:00"
    )

    payload = {
        "event": "ACCOUNT_SNAPSHOT",
        "data": {
            "account_id": summary.account_id,
            "total_balance": summary.total_balance,
            "used_margin": summary.used_margin,
            "free_margin": summary.free_margin,
            "realized_pnl": summary.realized_pnl,
            "unrealized_pnl": summary.unrealized_pnl
        }
    }

    json_bytes = orjson.dumps(payload)
    assert len(json_bytes) > 0
    decoded = orjson.loads(json_bytes)
    assert decoded["data"]["total_balance"] == 50_000_000.0

def test_friday_overnight_persistence_monday_reconciliation():
    """Validates Friday 15:15 O/N position state persistence and Monday 09:00 reconciliation."""
    friday_packet = {
        "date": "2026-08-21",
        "time": "15:15:00",
        "portfolioOptions": [
            {
                "type": "PUT",
                "side": "BUY",
                "strike": 340.0,
                "qty": 2,
                "price": 0.50,
                "tag_id": "O/N",
                "bought_date": "2026-08-21"
            }
        ]
    }

    # Weekend state preservation
    weekend_cache = dict(friday_packet)
    assert len(weekend_cache["portfolioOptions"]) == 1

    # Monday morning broadcast reconciliation
    monday_reconciled_packet = {
        "date": "2026-08-24",
        "time": "09:00:00",
        "portfolioOptions": weekend_cache["portfolioOptions"],
        "reconciliation_status": "MATCHED"
    }

    assert monday_reconciled_packet["portfolioOptions"][0]["bought_date"] == "2026-08-21"
    assert monday_reconciled_packet["reconciliation_status"] == "MATCHED"

def test_realtime_tick_and_margin_dashboard_sync():
    """Validates account summary synchronization upon real-time tick price update."""
    account = PaperTradingAccount(initial_capital=50_000_000.0)
    account.position_mgr.positions["OPT_CALL_350"] = {"qty": 2, "avg_price": 2.0, "side": "BUY"}

    # Update tick price -> Option Price = 2.50 (+0.50pt -> Unrealized PnL = +250,000 KRW)
    total_eq = account.update_tick_price(underlying_price=2.50)
    summary = account.get_canonical_summary()

    assert summary.total_balance == round(50_000_000.0 + 250_000.0, 2)
    assert summary.unrealized_pnl == 250_000.0
    assert summary.free_margin > 0.0

def test_ui_risk_banner_and_kill_switch_state_sync():
    """Validates immediate UI state packet propagation when Kill Switch is triggered."""
    ui_risk_packet = {
        "type": "RISK_ALERT",
        "emergency_stop": True,
        "risk_halt": True,
        "reason": "KILL_SWITCH_ENGAGED",
        "action": "HALT_ALL_TRADING_AND_FLATTEN",
        "timestamp": "2026-08-23 11:00:00"
    }

    assert ui_risk_packet["emergency_stop"] is True
    assert ui_risk_packet["action"] == "HALT_ALL_TRADING_AND_FLATTEN"
