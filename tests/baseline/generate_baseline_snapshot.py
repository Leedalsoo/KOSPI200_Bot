import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import orjson
from core.contracts import verify_account_integrity, OrderPurpose
import mock_ws_server as ws

def generate_snapshot():
    """대표 시나리오 baseline_snapshot_v1.json 스냅샷 생성"""
    ws._reset_session_state(preserve_capital=False)
    
    snapshot_data = {
        "scenario": "COVID_PANIC_2020_INITIAL",
        "seed": 42,
        "account": {
            "initial_capital": 25000000.0,
            "current_capital": ws.current_capital,
            "total_equity": ws.total_equity,
        },
        "pnl": {
            "realized_pnl": sum(ws.strategy_realized_pnl.values()),
            "unrealized_pnl": ws.total_equity - ws.current_capital,
            "strategy_pnl": sum(v for k, v in ws.strategy_pnl_tracker.items() if k != "Hedge"),
            "hedge_pnl": ws.strategy_pnl_tracker.get("Hedge", 0.0),
            "net_pnl": ws.total_equity - 25000000.0
        },
        "guards": {
            "is_market_opened_today": ws.is_market_opened_today,
            "already_rolled_this_month": ws.already_rolled_this_month
        },
        "positions_count": len(ws.portfolio_options)
    }
    
    os.makedirs(os.path.join("tests", "baseline"), exist_ok=True)
    snapshot_path = os.path.join("tests", "baseline", "baseline_snapshot_v1.json")
    with open(snapshot_path, "wb") as f:
        f.write(orjson.dumps(snapshot_data, option=orjson.OPT_INDENT_2))
    print(f"[BASELINE] Snapshot saved to {snapshot_path}")

if __name__ == "__main__":
    generate_snapshot()
