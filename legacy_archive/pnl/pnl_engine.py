# -*- coding: utf-8 -*-
from decimal import Decimal
from typing import Dict

from core.contracts import PnLSnapshot, ExecutionReport, OrderPurpose, calculate_weighted_average_price

class PnLEngine:
    """[Phase 6 Virtual Broker PnL Engine]
    
    Realized PnL, Unrealized PnL, Strategy PnL, Hedge PnL, Fee, Slippage, Net PnL
    7단 손익 항목을 독립 분해 연산하는 이중계상 방지 손익 엔진.
    """
    def __init__(self) -> None:
        self.realized_pnl = Decimal("0.00")
        self.unrealized_pnl = Decimal("0.00")
        self.strategy_realized_pnl: Dict[str, Decimal] = {}
        self.hedge_realized_pnl = Decimal("0.00")
        self.total_fee = Decimal("0.00")
        self.total_slippage = Decimal("0.00")

    def register_execution(self, report: ExecutionReport, entry_price: Decimal, multiplier: Decimal = Decimal("250000")) -> None:
        """체결 보고서를 받아 수수료, 슬리피지 및 (청산 시) 실현 손익을 집계"""
        self.total_fee += report.fee
        self.total_slippage += report.slippage_cost

        if report.order_purpose == OrderPurpose.STRATEGY_EXIT:
            # 청산 시 Realized PnL 계산
            pnl_per_qty = (report.execution_price - entry_price) * multiplier
            trade_pnl = pnl_per_qty * Decimal(str(report.filled_qty))
            
            self.realized_pnl += trade_pnl
            
            if report.order_purpose == OrderPurpose.RISK_HEDGE:
                self.hedge_realized_pnl += trade_pnl
            else:
                current_strat_pnl = self.strategy_realized_pnl.get(report.strategy_id, Decimal("0.00"))
                self.strategy_realized_pnl[report.strategy_id] = current_strat_pnl + trade_pnl

    def update_unrealized_pnl(self, total_unrealized: Decimal) -> None:
        """미실현 평가 손익(MTM) 갱신"""
        self.unrealized_pnl = total_unrealized

    def get_snapshot(self) -> PnLSnapshot:
        """7단 분해 손익 스냅샷 생성"""
        sum_strategy_pnl = sum(self.strategy_realized_pnl.values(), Decimal("0.00"))
        net_pnl = self.realized_pnl + self.unrealized_pnl - self.total_fee - self.total_slippage

        return PnLSnapshot(
            realized_pnl=self.realized_pnl,
            unrealized_pnl=self.unrealized_pnl,
            strategy_pnl=sum_strategy_pnl,
            hedge_pnl=self.hedge_realized_pnl,
            fee=self.total_fee,
            slippage=self.total_slippage,
            net_pnl=net_pnl
        )
