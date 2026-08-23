"""Virtual Market Simulator - Market Clock Module."""
from datetime import datetime, timedelta
from typing import Optional

class MarketClock:
    def __init__(self, start_time: Optional[datetime] = None, time_scale: float = 1.0):
        self.current_time = start_time or datetime.now()
        self.time_scale = time_scale

    def tick(self, milliseconds: int = 1000) -> datetime:
        self.current_time += timedelta(milliseconds=milliseconds * self.time_scale)
        return self.current_time

    def set_time(self, new_time: datetime) -> None:
        self.current_time = new_time
