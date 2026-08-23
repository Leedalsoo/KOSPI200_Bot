"""Virtual Market Simulator Runtime (VMS)."""
import logging
from typing import List, Generator, Optional, Dict, Any
from shared.contracts.canonical import CanonicalMarketTick
from virtual_market_simulator.market.synthetic_market_generator import (
    HistoricalReplayEngine,
    VirtualBrokerConfig,
    VirtualBrokerControlInterface
)

logger = logging.getLogger(__name__)

class VirtualMarketSimulatorRuntime:
    """[VMS 런타임: 마켓 데이터 스트리밍 및 시뮬레이션 시계 전담]"""
    def __init__(self, config: Optional[VirtualBrokerConfig] = None):
        self.config = config if config is not None else VirtualBrokerConfig()
        self.control = VirtualBrokerControlInterface(config=self.config)
        self.replay_engine = HistoricalReplayEngine(control_interface=self.control)
        self.current_seq: int = 0

    def step(self) -> Dict[str, Any]:
        tick = self.replay_engine.next_tick()
        if tick is None:
            self.replay_engine.load_scenario(self.config.scenario_name)
            tick = self.replay_engine.next_tick()
        return tick if tick is not None else {"price": 350.0, "bid": 349.95, "ask": 350.05, "timestamp": "2026-08-23 09:00:00"}

    def generate_tick_stream(self, total_days: int = 1250, ticks_per_day: int = 500) -> Generator[CanonicalMarketTick, None, None]:
        """[VMS 마켓 틱 스트림 생성기]"""
        self.replay_engine.load_scenario(self.config.scenario_name)
        total_ticks = total_days * ticks_per_day
        for _ in range(total_ticks):
            tick_dict = self.step()
            self.current_seq += 1
            yield CanonicalMarketTick(
                timestamp=str(tick_dict.get("timestamp", "2026-08-23 09:00:00")),
                underlying_price=float(tick_dict.get("price", 350.0)),
                strike_price=float(tick_dict.get("strike", 350.0)),
                option_type=str(tick_dict.get("option_type", "CALL")),
                bid_price=float(tick_dict.get("bid", 349.95)),
                ask_price=float(tick_dict.get("ask", 350.05)),
                last_price=float(tick_dict.get("price", 350.0)),
                volume=int(tick_dict.get("volume", 10)),
                seq_id=self.current_seq
            )

    def inject_scenario(self, scenario_name: str) -> None:
        self.config.scenario_name = scenario_name
        self.replay_engine.load_scenario(scenario_name)
        logger.info(f"[VMS] Scenario injected: {scenario_name}")
