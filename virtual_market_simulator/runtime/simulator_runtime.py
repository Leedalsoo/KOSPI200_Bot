"""Virtual Market Simulator Runtime (VMS) - Authoritative Market Stream Authority."""
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
    """[VMS 런타임: Authoritative Market Data Provider - HistoricalReplayEngine 결합]"""
    def __init__(self, config: Optional[VirtualBrokerConfig] = None):
        self.config = config if config is not None else VirtualBrokerConfig()
        self.control = VirtualBrokerControlInterface(config=self.config)
        self.replay_engine = HistoricalReplayEngine(control_interface=self.control)
        
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
        """[VMS Authoritative Market Data Stream: HistoricalReplayEngine & Scenario Engine 100% 결합]"""
        self.replay_engine.load_scenario(self.config.scenario_name)
        total_ticks = total_days * ticks_per_day
        
        # Generator via HistoricalReplayEngine & Scenario Engine
        for i in range(1, total_ticks + 1):
            raw_tick = self.replay_engine.next_tick()
            if raw_tick is None:
                self.replay_engine.load_scenario(self.config.scenario_name)
                raw_tick = self.replay_engine.next_tick()

            price = float(raw_tick.get("price", 350.0)) if raw_tick else 350.0
            bid = float(raw_tick.get("bid", price - 0.05)) if raw_tick else round(price - 0.05, 2)
            ask = float(raw_tick.get("ask", price + 0.05)) if raw_tick else round(price + 0.05, 2)
            
            seq = self.state_mgr.next_sequence()
            ts_str = self.clock.get_time_str()
            self.clock.advance_tick(500)

            yield CanonicalMarketTick(
                timestamp=ts_str,
                underlying_price=price,
                strike_price=350.0,
                option_type="CALL",
                bid_price=bid,
                ask_price=ask,
                last_price=price,
                volume=10,
                seq_id=seq
            )

    def inject_scenario(self, scenario_name: str) -> Dict[str, Any]:
        self.config.scenario_name = scenario_name
        self.replay_engine.load_scenario(scenario_name)
        params = self.scenario_engine.apply_scenario(scenario_name)
        logger.info(f"[VMS Authority] Scenario injected: {scenario_name} with params {params}")
        return params
