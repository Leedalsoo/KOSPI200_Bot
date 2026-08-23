"""Virtual Market Simulator Control Panel UI Interface."""
import logging
from typing import Dict, Any, Optional
from virtual_market_simulator.market.synthetic_market_generator import VirtualBrokerControlInterface

logger = logging.getLogger(__name__)

class MarketSimulatorUI:
    """[가상거래소 전용 UI 제어판]"""
    def __init__(self, control_interface: Optional[VirtualBrokerControlInterface] = None):
        self.control = control_interface if control_interface is not None else VirtualBrokerControlInterface()

    def render_simulator_dashboard(self) -> Dict[str, Any]:
        cfg = self.control.get_config()
        return {
            "title": "=== 가상거래소(VMS) 시뮬레이션 제어판 ===",
            "replay_speed": f"{cfg['replay_speed']}x",
            "scenario_name": cfg["scenario_name"],
            "volatility_scale": f"{cfg['volatility_scale']}x",
            "slippage_multiplier": f"{cfg['slippage_multiplier']}x",
            "base_spread_pt": f"{cfg['base_spread']}pt",
            "latency_ms": f"{cfg['latency_ms']}ms",
            "status": "RUNNING"
        }
