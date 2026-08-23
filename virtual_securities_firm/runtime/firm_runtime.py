"""Virtual Securities Firm Runtime (VSSF) - Authoritative Execution & OrderBook Matching."""
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
    """[VSSF 런타임: 실시간 주문 접수 ➔ 마진 검증 ➔ OrderBook 호가 매칭 ➔ 체결 이행 ➔ 계좌 Mutation]"""
    def __init__(self, initial_capital: float = 25000000.0):
        self.account = PaperTradingAccount(initial_capital=initial_capital)
        self.execution_engine = ExecutionEngine()
        self.slippage_engine = SlippageEngine()
        self.order_book = OrderBook(symbol="KOSPI200_OPTION")
        self.execution_history: List[CanonicalExecutionReport] = []

    def process_market_data(self, tick: CanonicalMarketTick) -> None:
        """[VSSF 마켓 게이트웨이: 시세 수신 ➔ 호가창(OrderBook) & 계좌 PnL 실시간 갱신]"""
        self.account.update_tick_price(tick.underlying_price)
        self.order_book.update_bid_ask(bid_price=tick.bid_price, ask_price=tick.ask_price)

    def process_order(self, command: CanonicalOrderCommand) -> Optional[CanonicalExecutionReport]:
        """[VSSF 체결 핵심 흐름]
        
        Order (CanonicalOrderCommand)
         ↓
        1. Margin Check (Broker Risk Admission)
         ↓
        2. OrderBook Matching (OrderBook.match_order()) -> 중심 체결 매칭
         ↓
        3. SlippageEngine Execution Calculation (호가 기반 슬리피지 연산)
         ↓
        4. Authoritative Account State Mutation (PaperTradingAccount.apply_execution())
         ↓
        5. Issue Canonical Execution Report
        """
        price = getattr(command, "price", 2.5)
        qty = getattr(command, "qty", 1)
        side_str = command.side.value if hasattr(command.side, "value") else str(command.side)

        # 1. Broker Margin Risk Check (증거금 리스크 검증)
        estimated_cost = price * qty * 250000
        free_margin = getattr(self.account.canonical_summary, "free_margin", 25000000.0)
        
        if side_str == "BUY" and free_margin < estimated_cost:
            logger.warning(f"[VSSF Risk Reject] Insufficient margin for order {command.client_order_id}")
            return None

        # 2. OrderBook Real Matching Engine (OrderBook 중심 실제 호가 매칭이 이행됨)
        match_result = self.order_book.match_order(command)
        if not match_result.get("is_filled", False):
            logger.warning(f"[VSSF OrderBook Reject] Order {command.client_order_id} could not be matched")
            return None

        matched_price = float(match_result.get("matched_price", price))
        matched_qty = int(match_result.get("matched_qty", qty))

        # 3. SlippageEngine Execution Calculation (호가 매칭 가격 기준 슬리피지 반영)
        slip_res = self.slippage_engine.calculate_execution(
            order_type="LIMIT",
            side=side_str,
            requested_price=matched_price,
            qty=matched_qty
        )
        exec_price = float(slip_res.get("executed_price", matched_price))
        slippage = float(slip_res.get("slippage", 0.0))
        fee = exec_price * matched_qty * 250000 * 0.000015  # 수수료 산출

        # 4. Authoritative Account State Mutation (실제 계좌 포지션/자산/PnL 갱신)
        self.account.apply_execution(
            track_id=getattr(command, "track_id", "Track1"),
            side=side_str,
            qty=matched_qty,
            price=exec_price,
            fee=fee
        )

        # 5. Issue Canonical Execution Report (체결 증명서 발급)
        report = CanonicalExecutionReport(
            exec_id=f"EXEC-{uuid.uuid4().hex[:8].upper()}",
            client_order_id=getattr(command, "client_order_id", "ORD-001"),
            track_id=getattr(command, "track_id", "Track1"),
            asset_type=getattr(command, "asset_type", CanonicalAssetType.OPTION),
            side=command.side,
            executed_qty=matched_qty,
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
