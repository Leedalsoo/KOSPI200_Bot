"""Unit test for Target Architecture UI control panels."""
import pytest
from virtual_securities_firm.control.firm_ui import SecuritiesFirmUI
from virtual_market_simulator.control.simulator_ui import MarketSimulatorUI
from virtual_securities_firm.execution.execution_ui import ExecutionUI

def test_securities_firm_ui_rendering() -> None:
    ui = SecuritiesFirmUI()
    dashboard = ui.render_account_dashboard()
    assert dashboard["status"] == "OPERATIONAL"
    assert "₩25,000,000" in dashboard["total_balance"]
    
    order_mon = ui.render_order_execution_monitor([])
    assert order_mon["total_orders"] == 0

def test_market_simulator_ui_rendering() -> None:
    sim_ui = MarketSimulatorUI()
    dash = sim_ui.render_simulator_dashboard()
    assert dash["status"] == "RUNNING"
    assert dash["replay_speed"] == "1x"

def test_execution_ui_rendering() -> None:
    exec_ui = ExecutionUI()
    exec_ui.log_execution({"order_id": "ORD-001", "price": 300.0})
    summary = exec_ui.render_execution_summary()
    assert summary["total_executions"] == 1
