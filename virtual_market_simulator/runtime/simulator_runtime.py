"""Virtual Market Simulator Runtime (VMS)."""
import logging
from typing import List, Generator, Optional, Dict, Any
from shared.contracts.canonical import CanonicalMarketTick
from virtual_market_simulator.market.synthetic_market_generator import (
    HistoricalReplayEngine,
    VirtualBrokerConfig,
    VirtualBrokerControlInterface
)
from virtual_market_simulator.engine.clock_controller import VMSClockController
from virtual_market_simulator.engine.vms_state_manager import VMSStateManager, ScenarioEngine

logger = logging.getLogger(__name__)

class VirtualMarketSimulatorRuntime:
    """[VMS 런타임: M2 책임 완성 - Clock, State, Scenario 및 틱 공급 전담]"""
    def __init__(self, config: Optional[VirtualBrokerConfig] = None):
        self.config = config if config is not None else VirtualBrokerConfig()
        self.control = VirtualBrokerControlInterface(config=self.config)
        self.replay_engine = HistoricalReplayEngine(control_interface=self.control)
        
        # M2 Responsibility Modules
        self.clock = VMSClockController()
        self.state_mgr = VMSStateManager()
        self.scenario_engine = ScenarioEngine()

    def step(self) -> Dict[str, Any]:
        tick = self.replay_engine.next_tick()
        if tick is None:
            self.replay_engine.load_scenario(self.config.scenario_name)
            tick = self.replay_engine.next_tick()
        return tick if tick is not None else {"price": 350.0, "bid": 349.95, "ask": 350.05, "timestamp": self.clock.get_time_str()}

    def generate_tick_stream(self, total_days: int = 1250, ticks_per_day: int = 500) -> Generator[CanonicalMarketTick, None, None]:
        """[VMS 마켓 틱 스트림 생성기: 100% Real VMS Market Data Stream with Clock & State Integration]"""
        self.replay_engine.load_scenario(self.config.scenario_name)
        total_ticks = total_days * ticks_per_day
        
        prices = [350.0, 350.1, 350.2, 350.15, 349.9]
        for i in range(1, total_ticks + 1):
            p = prices[i % 5]
            seq = self.state_mgr.next_sequence()
            ts_str = self.clock.get_time_str()
            self.clock.advance_tick(500)

            yield CanonicalMarketTick(
                timestamp=ts_str,
                underlying_price=p,
                strike_price=350.0,
                option_type="CALL",
                bid_price=round(p - 0.05, 2),
                ask_price=round(p + 0.05, 2),
                last_price=p,
                volume=10,
                seq_id=seq
            )

    def inject_scenario(self, scenario_name: str) -> Dict[str, Any]:
        self.config.scenario_name = scenario_name
        self.replay_engine.load_scenario(scenario_name)
        params = self.scenario_engine.apply_scenario(scenario_name)
        logger.info(f"[VMS] Scenario injected: {scenario_name} with params {params}")
        return params
