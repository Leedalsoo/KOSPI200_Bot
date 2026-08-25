"""Canonical tick replay source."""
from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import List, Optional

from shared.contracts.canonical import CanonicalMarketTick


class HistoricalReplayEngine:
    """Deterministic in-memory replay source for canonical market ticks."""

    def __init__(self, ticks: Optional[Iterable[CanonicalMarketTick]] = None) -> None:
        self._ticks: List[CanonicalMarketTick] = list(ticks or [])
        self._cursor = 0

    @property
    def active(self) -> bool:
        return bool(self._ticks)

    @property
    def exhausted(self) -> bool:
        return self._cursor >= len(self._ticks)

    @property
    def cursor(self) -> int:
        return self._cursor

    def load(self, ticks: Iterable[CanonicalMarketTick]) -> None:
        self._ticks = list(ticks)
        self._cursor = 0

    def clear(self) -> None:
        self._ticks = []
        self._cursor = 0

    def reset(self) -> None:
        self._cursor = 0

    def next_tick(self) -> Optional[CanonicalMarketTick]:
        if self.exhausted:
            return None
        tick = self._ticks[self._cursor]
        self._cursor += 1
        return tick

    def __iter__(self) -> Iterator[CanonicalMarketTick]:
        while True:
            tick = self.next_tick()
            if tick is None:
                return
            yield tick
