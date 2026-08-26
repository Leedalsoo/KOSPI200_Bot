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

logger = logging.getLogger(__name__)


class VirtualSecuritiesFirmRuntime:
    """VSSF authoritative runtime with deterministic UI control hooks."""

    _MARGIN_MODES = {"NORMAL", "TIGHT"}

    def __init__(self, initial_capital: float = 25000000.0):
        self.account = PaperTradingAccount(initial_capital=initial_capital)
        self.execution_engine = ExecutionEngine()
        self.order_book = OrderBook()
        self.reconciliation_engine = AuthoritativeReconciliationEngine(initial_capital=initial_capital)

        # M5 modules — authoritative path owner
        self.settlement_engine = SettlementEngine(account=self.account)
        self.recovery_engine = StateRecoveryEngine(account=self.account)
        self.margin_engine = self.account.margin_engine

        # Phase 5 control state. These values modify admission behavior only;
        # account/position/ledger ownership remains inside VSSF.
        self._margin_mode = "NORMAL"
        self._leverage = 1.0
        self._margin_call_pending = False
        self._margin_shortage_pending = False

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

    # ------------------------------------------------------------------
    # Phase 5: VSSF/Broker Control
    # ------------------------------------------------------------------
    def set_margin_mode(self, mode: str) -> None:
        value = str(mode).upper()
        if value not in self._MARGIN_MODES:
            raise ValueError(f"unsupported margin mode: {mode}")
        self._margin_mode = value

    def inject_margin_call(self) -> None:
        """Reject exactly the next order as a deterministic margin-call injection."""
        self._margin_call_pending = True

    def inject_margin_shortage(self) -> None:
        """Reject exactly the next order as a deterministic margin-shortage injection."""
        self._margin_shortage_pending = True

    def set_leverage(self, leverage: float) -> None:
        value = float(leverage)
        if value <= 0.0 or value > 20.0:
            raise ValueError("leverage must be greater than 0 and no more than 20")
        self._leverage = value

    def control_snapshot(self) -> Dict[str, Any]:
        return {
            "margin_mode": self._margin_mode,
            "leverage": self._leverage,
            "margin_call_pending": self._margin_call_pending,
            "margin_shortage_pending": self._margin_shortage_pending,
        }

    def _controlled_order_margin(self, command: CanonicalOrderCommand) -> float:
        base_margin = self.margin_engine.calculate_order_margin(command)
        mode_factor = 1.5 if self._margin_mode == "TIGHT" else 1.0
        return base_margin * mode_factor / self._leverage

    def process_market_data(self, tick: CanonicalMarketTick) -> None:
        self.metrics["market_ticks"] += 1
        self.order_book.update_bid_ask(tick.bid_price, tick.ask_price)
        self.account.update_tick_price(tick.underlying_price)
        self.metrics["pnl_updates"] += 1

    def process_order(self, command: CanonicalOrderCommand) -> Optional[CanonicalExecutionReport]:
        self.metrics["order_commands"] += 1

        # Phase 5 deterministic control injections are consumed once so the UI
        # can trigger a bounded test without permanently disabling trading.
        if self._margin_call_pending:
            self._margin_call_pending = False
            self.metrics["risk_rejected"] += 1
            logger.info("[VSSF Control] Margin call injection rejected order %s", command.client_order_id)
            return None

        if self._margin_shortage_pending:
            self._margin_shortage_pending = False
            self.metrics["risk_rejected"] += 1
            logger.info("[VSSF Control] Margin shortage injection rejected order %s", command.client_order_id)
            return None

        # MarginEngine remains the single calculation authority. Phase 5 only
        # applies the selected control factor to its result.
        margin_required = self._controlled_order_margin(command)

        if self.account.free_margin < margin_required:
            self.metrics["risk_rejected"] += 1
            logger.debug(
                "[VSSF Risk Rejected] Insufficient margin: %.2f < %.2f",
                self.account.free_margin,
                margin_required,
            )
            return None

        self.metrics["risk_accepted"] += 1

        matched_price = self.order_book.match_order(command)
        if isinstance(matched_price, dict):
            m_price = matched_price.get("matched_price", command.price)
        else:
            m_price = float(matched_price)

        if m_price <= 0:
            return None
        self.metrics["orderbook_matches"] += 1

        report = self.execution_engine.execute_order(command, m_price, command.qty)
        if report:
            self.metrics["executions_issued"] += 1
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
            current_positions=self.account.positions,
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
