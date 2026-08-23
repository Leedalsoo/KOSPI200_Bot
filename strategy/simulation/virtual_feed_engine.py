"""Legacy Virtual Feed Engine Adapter (Delegating to VMS and VSSF Target Architecture Owners)."""
import logging
from virtual_market_simulator.market.synthetic_market_generator import (
    VirtualBrokerConfig,
    VirtualBrokerControlInterface,
    HistoricalReplayEngine
)
from virtual_securities_firm.execution.execution_engine import SlippageEngine
from virtual_securities_firm.account.paper_account import PaperTradingAccount

logger = logging.getLogger(__name__)

__all__ = [
    "VirtualBrokerConfig",
    "VirtualBrokerControlInterface",
    "HistoricalReplayEngine",
    "SlippageEngine",
    "PaperTradingAccount"
]
