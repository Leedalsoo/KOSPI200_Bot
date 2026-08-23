"""Virtual Securities Firm Runtime (VSSF) - Full Authoritative Pipeline Execution."""
import logging
from typing import Optional, Dict, Any
from shared.contracts.canonical import (
    CanonicalMarketTick,
    CanonicalOrderCommand,
    CanonicalExecutionReport,
)
from virtual_securities_firm.account.paper_account import PaperTradingAccount
from virtual_securities_firm.execution.execution_engine import ExecutionEngine
from virtual_securities_firm.exchange.order_book import OrderBook
from virtual_securities_firm.account.reconciliation import AuthoritativeReconciliationEngine
from virtual_securities_firm.settlement.settlement_engine import SettlementEngine
from virtual_securities_firm.recovery.state_recovery import StateRecoveryEngine
from virtual_securities_firm.margin.margin_engine import MarginEngine

logger = logging.getLogger(__name__)

class VirtualSecuritiesFirmRuntime:
    """[VSSF 런타임: M4~M5 완수 — MarginEngine 책임 이관 완료, 직접 계산 0]"""
    def __init__(self, initial_capital: float = 25000000.0):
        self.account = PaperTradingAccount(initial_capital=initial_capital)
        self.execution_engine = ExecutionEngine()
        self.order_book = OrderBook()
        self.reconciliation_engine = AuthoritativeReconciliationEngine(initial_capital=initial_capital)

        # M5 Modules — authoritative path owner
        self.settlement_engine = SettlementEngine(account=self.account)
        self.recovery_engine = StateRecoveryEngine(account=self.account)
        # MarginEngine: 단일 권위자 확정 (PaperTradingAccount 소유 인스턴스 단일 공유)
        self.margin_engine = self.account.margin_engine

        self.metrics: Dict[str, int] = {
            "market_ticks": 0,
            "strategy_signals": 0,
            "order_commands": 0,
            "risk_accepted": 0,
            "risk_rejected": 0,
            "orderbook_matches": 0,
            "executions_issued": 0,
            "account_mutations": 0,
            "position_mutations": 0,
            "pnl_updates": 0,
            "reconciliation_checks": 0,
            "settlement_runs": 0,
        }

    @property
    def orderbook(self) -> OrderBook:
        """하위 호환성을 위한 orderbook 프로퍼티 alias"""
        return self.order_book

    def cancel_order(self, client_order_id: str) -> bool:
        """주문 취소 위임"""
        return self.order_book.cancel_order(client_order_id)

    def process_market_data(self, tick: CanonicalMarketTick) -> None:
        self.metrics["market_ticks"] += 1
        self.order_book.update_bid_ask(tick.bid_price, tick.ask_price)
        self.account.update_tick_price(tick.underlying_price)
        self.metrics["pnl_updates"] += 1

    def process_order(self, command: CanonicalOrderCommand) -> Optional[CanonicalExecutionReport]:
        self.metrics["order_commands"] += 1

        # [Risk Admission Guard] — MarginEngine 단독 책임, firm_runtime 직접 계산 없음
        margin_required = self.margin_engine.calculate_order_margin(command)

        if self.account.free_margin < margin_required:
            self.metrics["risk_rejected"] += 1
            logger.debug(
                "[VSSF Risk Rejected] Insufficient margin: %.2f < %.2f",
                self.account.free_margin, margin_required
            )
            return None

        self.metrics["risk_accepted"] += 1

        # OrderBook Matching
        matched_price = self.order_book.match_order(command)
        if isinstance(matched_price, dict):
            m_price = matched_price.get("matched_price", command.price)
        else:
            m_price = float(matched_price)

        if m_price <= 0:
            return None
        self.metrics["orderbook_matches"] += 1

        # Execution Engine
        report = self.execution_engine.execute_order(command, m_price, command.qty)
        if report:
            self.metrics["executions_issued"] += 1

            # Account, Position & Ledger Mutation (Authoritative chain)
            self.account.apply_execution(report)
            self.metrics["account_mutations"] += 1
            self.metrics["position_mutations"] += 1

        return report

    def run_settlement(self, final_settlement_price: Optional[float] = None) -> Dict[str, Any]:
        """[M5 Authoritative Settlement] 일일 MTM 정산 및 정산 장부 기록"""
        price = final_settlement_price if final_settlement_price is not None else 350.0
        record = self.settlement_engine.perform_eod_settlement(price)
        self.metrics["settlement_runs"] += 1
        return record

    def get_account_snapshot(self):
        return self.account.get_canonical_summary()

    def run_reconciliation(self) -> Dict[str, Any]:
        snap = self.account.get_canonical_summary()
        result = self.reconciliation_engine.reconcile_state(
            account_snapshot=snap,
            execution_history=self.execution_engine.reports,
            current_positions=self.account.positions
        )
        self.metrics["reconciliation_checks"] += 1
        return result

    def create_recovery_snapshot(self, sequence_id: int):
        snap = self.recovery_engine.create_snapshot(sequence_id, metrics=self.metrics)
        snap["execution_reports"] = list(self.execution_engine.reports)
        return snap

    def restore_recovery_snapshot(self, snapshot):
        ok = self.recovery_engine.restore_from_snapshot(snapshot, target_metrics=self.metrics)
        if ok and isinstance(snapshot, dict) and "execution_reports" in snapshot:
            self.execution_engine.reports = list(snapshot["execution_reports"])
        return ok


