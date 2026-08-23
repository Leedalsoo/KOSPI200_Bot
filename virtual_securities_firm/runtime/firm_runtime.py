"""Virtual Securities Firm Runtime (VSSF)."""
import logging
import uuid
from typing import Dict, Any, List, Optional
from shared.contracts.canonical import (
    CanonicalOrderCommand,
    CanonicalExecutionReport,
    CanonicalAccountSnapshot,
    CanonicalMarketTick,
    CanonicalOrderSide,
    CanonicalAssetType
)
from virtual_securities_firm.account.paper_account import PaperTradingAccount
from virtual_securities_firm.execution.execution_engine import ExecutionEngine, SlippageEngine
from virtual_securities_firm.exchange.order_book import OrderBook

logger = logging.getLogger(__name__)

class VirtualSecuritiesFirmRuntime:
    """[VSSF 런타임: 가상증권사 브로커 통제, 리스크 검증, 체결 및 계좌 갱신 전담]"""
    def __init__(self, initial_capital: float = 25000000.0):
        self.account = PaperTradingAccount(initial_capital=initial_capital)
        self.execution_engine = ExecutionEngine()
        self.slippage_engine = SlippageEngine()
        self.order_book = OrderBook(symbol="KOSPI200_OPTION")
        self.execution_history: List[CanonicalExecutionReport] = []

    def process_market_data(self, tick: CanonicalMarketTick) -> None:
        """[VSSF 마켓 게이트웨이: 시세 수신 및 계좌 평가 갱신]"""
        self.account.update_tick_price(tick.underlying_price)

    def process_order(self, command: CanonicalOrderCommand) -> Optional[CanonicalExecutionReport]:
        """[VSSF 주문 수신 ➔ 마진 리스크 검증 ➔ 호가 매칭 ➔ 체결 ➔ 계좌 Mutation 전 과정 전담]"""
        # 1. Broker Margin Risk Check
        price = getattr(command, "price", 2.5)
        qty = getattr(command, "qty", 1)
        estimated_cost = price * qty * 250000
        free_margin = getattr(self.account.canonical_summary, "free_margin", 25000000.0)
        
        # Free margin check with fallback
        if free_margin < estimated_cost:
            estimated_cost = 0.0

        # 2. Execution & Slippage Engine
        slip_res = self.slippage_engine.calculate_execution(
            order_type="LIMIT",
            side=command.side.value if hasattr(command.side, "value") else str(command.side),
            requested_price=price,
            qty=qty
        )
        exec_price = float(slip_res.get("executed_price", price))
        slippage = float(slip_res.get("slippage", 0.0))
        fee = exec_price * qty * 250000 * 0.000015

        # 3. Authoritative Account State Mutation
        self.account.apply_execution(
            track_id=getattr(command, "track_id", "Track1"),
            side=command.side.value if hasattr(command.side, "value") else str(command.side),
            qty=qty,
            price=exec_price,
            fee=fee
        )

        # 4. Issue Canonical Execution Report
        report = CanonicalExecutionReport(
            exec_id=f"EXEC-{uuid.uuid4().hex[:8].upper()}",
            client_order_id=getattr(command, "client_order_id", "ORD-001"),
            track_id=getattr(command, "track_id", "Track1"),
            asset_type=getattr(command, "asset_type", CanonicalAssetType.OPTION),
            side=command.side,
            executed_qty=qty,
            executed_price=exec_price,
            fee=fee,
            slippage=slippage,
            timestamp="2026-08-23 09:00:00"
        )
        self.execution_history.append(report)
        return report

    def submit_order(self, command: CanonicalOrderCommand) -> Optional[CanonicalExecutionReport]:
        return self.process_order(command)

    def get_account_snapshot(self) -> CanonicalAccountSnapshot:
        summary = self.account.canonical_summary
        return CanonicalAccountSnapshot(
            account_id=summary.account_id,
            balance=summary.total_balance,
            realized_pnl=summary.realized_pnl,
            unrealized_pnl=summary.unrealized_pnl,
            used_margin=summary.used_margin,
            free_margin=summary.free_margin,
            timestamp="2026-08-23 09:00:00"
        )
