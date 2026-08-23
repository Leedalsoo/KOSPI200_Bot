"""Virtual Securities Firm Runtime (VSSF) - Full Authoritative Pipeline Execution."""
import logging
from typing import Optional, Dict, Any
from shared.contracts.canonical import (
    CanonicalMarketTick,
    CanonicalOrderCommand,
    CanonicalExecutionReport,
    CanonicalAssetType
)
from virtual_securities_firm.account.paper_account import PaperTradingAccount
from virtual_securities_firm.execution.execution_engine import ExecutionEngine
from virtual_securities_firm.exchange.order_book import OrderBook
from virtual_securities_firm.account.reconciliation import AuthoritativeReconciliationEngine
from virtual_securities_firm.settlement.settlement_engine import SettlementEngine
from virtual_securities_firm.recovery.state_recovery import StateRecoveryEngine

logger = logging.getLogger(__name__)

class VirtualSecuritiesFirmRuntime:
    """[VSSF 런타임: M4~M5 완수 - 가상증권사 매칭/체결/계좌/정산/복구/Reconciliation 전담]"""
    def __init__(self, initial_capital: float = 25000000.0):
        self.account = PaperTradingAccount(initial_capital=initial_capital)
        self.execution_engine = ExecutionEngine()
        self.order_book = OrderBook()
        self.reconciliation_engine = AuthoritativeReconciliationEngine(initial_capital=initial_capital)
        
        # M5 Modules
        self.settlement_engine = SettlementEngine(account=self.account)
        self.recovery_engine = StateRecoveryEngine(account=self.account)

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
            "reconciliation_checks": 0
        }

    def process_market_data(self, tick: CanonicalMarketTick) -> None:
        self.metrics["market_ticks"] += 1
        self.order_book.update_bid_ask(tick.bid_price, tick.ask_price)
        self.account.update_tick_price(tick.underlying_price)
        self.metrics["pnl_updates"] += 1

    def process_order(self, command: CanonicalOrderCommand) -> Optional[CanonicalExecutionReport]:
        self.metrics["order_commands"] += 1
        
        # Risk Admission Guard (Asset Type & Option Premium Granular Risk Evaluation)
        multiplier = 250000.0
        if command.asset_type == CanonicalAssetType.OPTION:
            # Option Premium (e.g. 2.5pt) * qty * 250,000
            opt_price = command.price if command.price < 50.0 else 2.5
            margin_required = opt_price * command.qty * multiplier
        else:
            # Futures Margin (10% Initial Margin Ratio)
            margin_required = command.price * command.qty * multiplier * 0.10

        if self.account.free_margin < margin_required:
            self.metrics["risk_rejected"] += 1
            logger.debug(f"[VSSF Risk Rejected] Insufficient margin: {self.account.free_margin:.2f} < {margin_required:.2f}")
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
            
            # Account & Position Mutation
            self.account.apply_execution(report)
            self.metrics["account_mutations"] += 1
            self.metrics["position_mutations"] += 1

        return report

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
        return self.recovery_engine.create_snapshot(sequence_id)

    def restore_recovery_snapshot(self, snapshot):
        return self.recovery_engine.restore_from_snapshot(snapshot)
