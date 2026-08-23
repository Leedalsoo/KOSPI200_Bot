"""Virtual Securities Firm Runtime (VSSF) - Authoritative 10-Step Execution & Reconciliation Pipeline."""
import logging
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
from virtual_securities_firm.execution.execution_engine import ExecutionEngine
from virtual_securities_firm.exchange.order_book import OrderBook
from virtual_securities_firm.account.reconciliation import AuthoritativeReconciliationEngine

logger = logging.getLogger(__name__)

class VirtualSecuritiesFirmRuntime:
    """[VSSF 런타임: 10단계 핵심 파이프라인 소유 및 Reconciliation Auditing]
    
    1. Market  : process_market_data()
    2. Signal  : OptionProgram에서 검증 및 도달
    3. Order   : CanonicalOrderCommand
    4. Risk    : Broker Margin Risk Admission
    5. OrderBook: OrderBook.match_order()
    6. Execution: ExecutionEngine.execute_order()
    7. Account : PaperTradingAccount.apply_execution()
    8. Position: PaperTradingAccount 포지션 장부
    9. PnL     : PaperTradingAccount 손익 정산
    10. Reconciliation: AuthoritativeReconciliationEngine audit
    """
    def __init__(self, initial_capital: float = 25000000.0):
        self.account = PaperTradingAccount(initial_capital=initial_capital)
        self.execution_engine = ExecutionEngine()
        self.order_book = OrderBook(symbol="KOSPI200_OPTION")
        self.reconciliation_engine = AuthoritativeReconciliationEngine(initial_capital=initial_capital)
        self.execution_history: List[CanonicalExecutionReport] = []

    def process_market_data(self, tick: CanonicalMarketTick) -> None:
        """[Step 1: Market Gateway] 시세 수신 ➔ 호가창 & 계좌 PnL 갱신"""
        self.account.update_tick_price(tick.underlying_price)
        self.order_book.update_bid_ask(bid_price=tick.bid_price, ask_price=tick.ask_price)

    def process_order(self, command: CanonicalOrderCommand) -> Optional[CanonicalExecutionReport]:
        """[Step 3 ~ 9: Order -> Risk -> OrderBook -> Execution -> Account -> Position -> PnL]"""
        price = getattr(command, "price", 2.5)
        qty = getattr(command, "qty", 1)
        side_str = command.side.value if hasattr(command.side, "value") else str(command.side)

        # Step 4: Risk Check (증거금 검증)
        estimated_cost = price * qty * 250000
        free_margin = getattr(self.account.canonical_summary, "free_margin", 25000000.0)
        
        if side_str == "BUY" and free_margin < estimated_cost:
            logger.warning(f"[VSSF Risk Reject] Insufficient margin for order {command.client_order_id}")
            return None

        # Step 5: OrderBook Insertion & Matching
        match_result = self.order_book.match_order(command)
        if not match_result.get("is_filled", False):
            logger.warning(f"[VSSF OrderBook Reject] Order {command.client_order_id} could not be matched")
            return None

        matched_price = float(match_result.get("matched_price", price))
        matched_qty = int(match_result.get("matched_qty", qty))

        # Step 6: Execution Engine Invocation
        report = self.execution_engine.execute_order(
            command=command,
            fill_price=matched_price,
            fill_qty=matched_qty
        )

        # Step 7~9: Account, Position, PnL Mutation
        self.account.apply_execution(
            track_id=report.track_id,
            side=side_str,
            qty=report.executed_qty,
            price=report.executed_price,
            fee=report.fee
        )

        self.execution_history.append(report)
        return report

    def run_reconciliation(self) -> Dict[str, Any]:
        """[Step 10: Reconciliation Auditing]"""
        snap = self.get_account_snapshot()
        positions = self.account.get_positions() if hasattr(self.account, "get_positions") else {}
        return self.reconciliation_engine.reconcile_state(
            account_snapshot=snap,
            execution_history=self.execution_history,
            current_positions=positions
        )

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
