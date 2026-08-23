"""Margin Engine for VSSF M5 Responsibility Decomposition."""
from typing import Dict, Any

class MarginEngine:
    """[M5 마진 엔진: 사용 증거금 및 가용 증거금 독점 계산]"""
    def __init__(self, initial_capital: float = 25000000.0):
        self.initial_capital = initial_capital

    def calculate_used_margin(self, positions: Dict[str, Dict[str, Any]], multiplier: float = 250000.0) -> float:
        used = 0.0
        for pos in positions.values():
            used += pos["avg_price"] * pos["qty"] * multiplier
        return round(used, 2)

    def calculate_free_margin(self, total_equity: float, used_margin: float) -> float:
        return max(0.0, total_equity - used_margin)
