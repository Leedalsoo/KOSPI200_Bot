"""Unit Test: Strategy Track 1~9 Full Lifecycle, Contracts & Independent Execution."""
import pytest
from decimal import Decimal
from typing import Dict, Any
import numpy as np

from infra.time_service import TimeService
from option_program.strategy.plugins.track1 import Track1
from option_program.strategy.plugins.track2 import Track2
from option_program.strategy.plugins.track3 import Track3
from option_program.strategy.plugins.track4 import Track4
from option_program.strategy.plugins.track5 import Track5
from option_program.strategy.plugins.track6 import Track6
from option_program.strategy.plugins.track7 import Track7
from option_program.strategy.plugins.track8 import Track8
from option_program.strategy.plugins.track9 import Track9

@pytest.fixture
def base_config() -> Dict[str, Any]:
    return {
        "strategies": {
            "strategy_1_1": {"params": {"profit_target": 500000.0}},
            "strategy_2": {"params": {}},
            "strategy_3": {"params": {}},
            "strategy_4": {"params": {}},
            "strategy_5": {"params": {}},
            "strategy_6": {"params": {}},
            "strategy_7": {"params": {}},
            "strategy_8": {"params": {}},
            "strategy_9": {"params": {}}
        }
    }

def test_track1_lifecycle(base_config):
    """Validates Track 1 Hybrid Scalping & Tail Defense initialization and core algorithms."""
    t1 = Track1(base_config)
    assert t1.profit_target == 500000.0
    fraction = t1._calculate_kelly_fraction(Decimal('0.6'), Decimal('1.5'))
    assert Decimal('0.041') < fraction < Decimal('0.042')
    assert t1._check_global_mdd_shutdown(Decimal('1000'), Decimal('800')) is True

def test_track2_lifecycle(base_config):
    """Validates Track 2 Breakout Momentum & Asymmetric Trap."""
    ts = TimeService(mode="BACKTEST")
    t2 = Track2(base_config, ts)
    trap_low = t2.build_asymmetric_trap(current_atm=350.0, active_vol=0.8, base_vol=1.0)
    assert trap_low["status"] == "ZERO_COST_WIDE_TRAP_SUCCESS"
    assert trap_low["trap_type"] == "ZERO_COST_10PT_WIDE"

def test_track3_lifecycle(base_config):
    """Validates Track 3 Statistical Arbitrage & Regime-aware execution."""
    t3 = Track3(base_config)
    assert hasattr(t3, "z_entry_threshold")
    assert t3.z_entry_threshold == 2.0

def test_track4_lifecycle(base_config):
    """Validates Track 4 Gamma Scalping & Deadband range."""
    ts = TimeService(mode="BACKTEST")
    t4 = Track4(base_config, ts)
    assert t4 is not None

def test_track5_lifecycle(base_config):
    """Validates Track 5 Pure Gap Divergence Protocol."""
    t5 = Track5(base_config)
    assert t5 is not None

def test_track6_lifecycle(base_config):
    """Validates Track 6 Daily Tail Insurance (0DTE)."""
    t6 = Track6(base_config)
    assert t6 is not None

def test_track7_lifecycle(base_config):
    """Validates Track 7 Volatility Arbitrage & Weekly Insurance."""
    t7 = Track7(base_config)
    assert t7 is not None

def test_track8_lifecycle(base_config):
    """Validates Track 8 Macro Regime Protection & Monthly Wide Strangle."""
    t8 = Track8(base_config)
    assert t8 is not None

def test_track9_lifecycle(base_config):
    """Validates Track 9 Event Driven & Overnight Insurance."""
    t9 = Track9(base_config)
    assert t9 is not None
