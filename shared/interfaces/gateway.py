"""Market Data Gateway Interface for M3 Broker Boundary."""
from typing import Generator
from shared.contracts.canonical import CanonicalMarketTick

class MarketDataGateway:
    """[M3 마켓 데이터 게이트웨이: VMS 틱 공급 및 브로커 틱 중계 표준 전담]"""
    def __init__(self, vms_runtime):
        self.vms_runtime = vms_runtime

    def stream_ticks(self, total_days: int = 1250, ticks_per_day: int = 500) -> Generator[CanonicalMarketTick, None, None]:
        return self.vms_runtime.generate_tick_stream(total_days=total_days, ticks_per_day=ticks_per_day)
