"""Unit Test: Control Panel & Orchestrator Comprehensive Verification."""
import pytest
from virtual_market_simulator.market.synthetic_market_generator import (
    VirtualBrokerConfig,
    VirtualBrokerControlInterface,
    HistoricalReplayEngine
)
from virtual_securities_firm.control.firm_ui import SecuritiesFirmUI
from virtual_securities_firm.account.paper_account import PaperTradingAccount
from sensor.trade_replay_analyzer import TradeReplayAnalyzer

def test_control_panel_speed_and_multipliers():
    """Validates control panel speed and simulation parameter multipliers and clamping."""
    control = VirtualBrokerControlInterface()

    # 1. Replay speed 1000x
    control.update_config({"replay_speed": 1000})
    assert control.get_config()["replay_speed"] == 1000

    # 2. Slippage multiplier clamping
    control.update_config({"slippage_multiplier": 0.1})
    assert control.get_config()["slippage_multiplier"] == 0.5
    control.update_config({"slippage_multiplier": 5.0})
    assert control.get_config()["slippage_multiplier"] == 3.0

    # 3. Fee rate multiplier clamping
    control.update_config({"fee_rate_multiplier": 0.2})
    assert control.get_config()["fee_rate_multiplier"] == 0.5
    control.update_config({"fee_rate_multiplier": 4.0})
    assert control.get_config()["fee_rate_multiplier"] == 2.0

    # 4. Volatility scale clamping
    control.update_config({"volatility_scale": 0.1})
    assert control.get_config()["volatility_scale"] == 0.5
    control.update_config({"volatility_scale": 4.5})
    assert control.get_config()["volatility_scale"] == 3.0

def test_control_panel_gap_injection_and_presets():
    """Validates gap injection and market regime presets."""
    control = VirtualBrokerControlInterface()
    control.update_config({"gap_pct": 0.02})  # +2.0% gap
    replay = HistoricalReplayEngine(control_interface=control)
    replay.load_scenario("GAP_SPIKE", start_price=300.0)

    tick = replay.next_tick()
    assert tick is not None
    assert tick["price"] >= 305.0

    presets = ["COVID_PANIC_2020", "BULL_TREND", "BEAR_TREND", "SIDEWAYS_BOX", "GAP_SPIKE"]
    for preset in presets:
        replay.load_scenario(preset, start_price=350.0)
        assert replay.is_active is True
        t = replay.next_tick()
        assert t is not None
        assert "price" in t

def test_securities_firm_ui_orchestration():
    """Validates SecuritiesFirmUI account dashboard and execution monitor rendering."""
    account = PaperTradingAccount(initial_capital=50_000_000.0)
    account.realized_pnl = 1_000_000.0
    account.unrealized_pnl = 500_000.0
    account.used_margin = 10_000_000.0
    account.free_margin = 41_500_000.0

    account.get_canonical_summary()
    ui = SecuritiesFirmUI(account=account)
    dash = ui.render_account_dashboard()
    assert dash["status"] == "OPERATIONAL"
    assert "₩51,500,000" in dash["total_balance"]
    assert "₩1,000,000" in dash["realized_pnl"]

    exec_monitor = ui.render_order_execution_monitor([{"order_id": "ORD_1"}, {"order_id": "ORD_2"}])
    assert exec_monitor["total_orders"] == 2
    assert len(exec_monitor["recent_orders"]) == 2

def test_orchestrator_speed_determinism_500x_1000x():
    """Validates deterministic tick price equivalence across 1x, 500x, and 1000x speeds."""
    c1 = VirtualBrokerControlInterface()
    c1.update_config({"replay_speed": 1})
    r1 = HistoricalReplayEngine(control_interface=c1)
    r1.load_scenario("COVID_PANIC_2020", start_price=300.0)

    c500 = VirtualBrokerControlInterface()
    c500.update_config({"replay_speed": 500})
    r500 = HistoricalReplayEngine(control_interface=c500)
    r500.load_scenario("COVID_PANIC_2020", start_price=300.0)

    c1000 = VirtualBrokerControlInterface()
    c1000.update_config({"replay_speed": 1000})
    r1000 = HistoricalReplayEngine(control_interface=c1000)
    r1000.load_scenario("COVID_PANIC_2020", start_price=300.0)

    ticks1 = [r1.next_tick() for _ in range(15)]
    ticks500 = [r500.next_tick() for _ in range(15)]
    ticks1000 = [r1000.next_tick() for _ in range(15)]

    for t1, t500, t1000 in zip(ticks1, ticks500, ticks1000):
        assert t1["price"] == t500["price"] == t1000["price"]
        assert t1["active_vol"] == t500["active_vol"] == t1000["active_vol"]

def test_time_bucket_pnl_diagnostic_report():
    """Validates time-bucket trade capture and diagnostic report generation."""
    analyzer = TradeReplayAnalyzer(mode="VIRTUAL")
    analyzer.capture_trade_event(
        trade_type="EXIT",
        track_name="Track1",
        side="SELL",
        asset_type="OPTION",
        price=2.50,
        qty=2,
        reason="Target Profit",
        realized_pnl=500000.0,
        sensor_snapshot={},
        state_snapshot={},
        date_str="2026-08-23 09:03:00",
        fee=37.5,
        slippage_cost=0.02
    )

    report = analyzer.generate_trade_analysis_report()
    assert "time_bucket_analysis" in report
    assert "T1_GAP_OPEN" in report["time_bucket_analysis"]
    assert report["time_bucket_analysis"]["T1_GAP_OPEN"]["Track1"]["net_pnl"] == 500000.0
