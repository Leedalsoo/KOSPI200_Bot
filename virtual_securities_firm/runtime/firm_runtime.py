"""Virtual Securities Firm Runtime (VSSF) - Authoritative Execution & Account Mutation."""
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
    """[VSSF 런타임: 실시간 주문 접수 ➔ 리스크 검증 ➔ 호가 매칭 ➔ 체결 이행 ➔ 계좌 Mutation & PnL 연산 전담]"""
    def __init__(self, initial_capital: float = 25000000.0):
        self.account = PaperTradingAccount(initial_capital=initial_capital)
        self.execution_engine = ExecutionEngine()
        self.slippage_engine = SlippageEngine()
        self.order_book = OrderBook(symbol="KOSPI200_OPTION")
        self.execution_history: List[CanonicalExecutionReport] = []

    def process_market_data(self, tick: CanonicalMarketTick) -> None:
        """[VSSF 마켓 게이트웨이: 시세 수신 및 실시간 호가창/계좌 PnL 평가 갱신]"""
        self.account.update_tick_price(tick.underlying_price)
        self.order_book.update_bid_ask(bid_price=tick.bid_price, ask_price=tick.ask_price)

    def process_order(self, command: CanonicalOrderCommand) -> Optional[CanonicalExecutionReport]:
        """[VSSF 주문 수신 ➔ 마진 리스크 검증 ➔ 호가 매칭 ➔ 체결 이행 ➔ 계좌 Mutation 전 과정 전담]"""
        price = getattr(command, "price", 2.5)
        qty = getattr(command, "qty", 1)
        side_str = command.side.value if hasattr(command.side, "value") else str(command.side)

        # 1. Broker Margin Risk Check
        estimated_cost = price * qty * 250000
        free_margin = getattr(self.account.canonical_summary, "free_margin", 25000000.0)
        
        if side_str == "BUY" and free_margin < estimated_cost:
            logger.warning(f"[VSSF Risk Reject] Insufficient margin for order {command.client_order_id}")
            return None

        # 2. Execution & Slippage Engine (실제 호가 매칭 및 체결 가격 연산)
        slip_res = self.slippage_engine.calculate_execution(
            order_type="LIMIT",
            side=side_str,
            requested_price=price,
            qty=qty
        )
        exec_price = float(slip_res.get("executed_price", price))
        slippage = float(slip_res.get("slippage", 0.0))
        fee = exec_price * qty * 250000 * 0.000015  # 수수료 산출

        # 3. Authoritative Account State Mutation & Realized PnL Update
        self.account.apply_execution(
            track_id=getattr(command, "track_id", "Track1"),
            side=side_str,
            qty=qty,
            price=exec_price,
            fee=fee
        )

        # 4. Issue Canonical Execution Report (체결 증명서 발급)
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
