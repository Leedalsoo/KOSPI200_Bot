"""Margin Engine for VSSF M5 Responsibility Decomposition."""
from typing import Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from shared.contracts.canonical import CanonicalOrderCommand, CanonicalAssetType

MULTIPLIER = 250000.0
FUTURES_INITIAL_MARGIN_RATIO = 0.10
OPTION_PRICE_SANITY_CAP = 50.0
OPTION_PRICE_FALLBACK = 2.5


class MarginEngine:
    """[M5 마진 엔진: 주문 증거금·포지션 증거금·가용 증거금 독점 계산 — firm_runtime 직접 계산 완전 이관]"""

    def __init__(self, initial_capital: float = 25000000.0):
        self.initial_capital = initial_capital

    def calculate_order_margin(self, command: Any) -> float:
        """[Risk Admission Guard] 주문 한 건에 필요한 증거금 산출.

        firm_runtime.process_order() 의 직접 계산을 대체한다.
        command: CanonicalOrderCommand (타입 순환 참조 방지를 위해 Any 사용)
        """
        from shared.contracts.canonical import CanonicalAssetType  # noqa: PLC0415
        if command.asset_type == CanonicalAssetType.OPTION:
            opt_price = command.price if command.price < OPTION_PRICE_SANITY_CAP else OPTION_PRICE_FALLBACK
            return opt_price * command.qty * MULTIPLIER
        else:
            # Futures: 10% Initial Margin
            return command.price * command.qty * MULTIPLIER * FUTURES_INITIAL_MARGIN_RATIO

    def calculate_used_margin(self, positions: Dict[str, Dict[str, Any]], multiplier: float = MULTIPLIER) -> float:
        """보유 포지션 기준 사용 증거금 합산"""
        used = 0.0
        for pos in positions.values():
            used += pos["avg_price"] * pos["qty"] * multiplier
        return round(used, 2)

    def calculate_free_margin(self, total_equity: float, used_margin: float) -> float:
        """가용 증거금 = max(0, total_equity - used_margin)"""
        return max(0.0, total_equity - used_margin)
