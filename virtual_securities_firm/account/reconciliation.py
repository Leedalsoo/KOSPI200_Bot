"""Virtual Securities Firm - Authoritative Reconciliation & State Integrity Engine."""
import logging
from typing import Dict, Any, List, Optional, Set
from shared.contracts.canonical import CanonicalExecutionReport
from virtual_securities_firm.position.position_manager import PositionManager
from virtual_securities_firm.margin.margin_engine import MarginEngine, MULTIPLIER

logger = logging.getLogger(__name__)


class AuthoritativeReconciliationEngine:
    """[VSSF 소유] 10단계 파이프라인 상태 정합성 Auditing & Reconciliation Engine."""

    def __init__(self, initial_capital: float = 25000000.0, multiplier: float = MULTIPLIER):
        self.initial_capital = initial_capital
        self.multiplier = multiplier
        self.margin_engine = MarginEngine(initial_capital=initial_capital)
        self.last_report: Optional[Dict[str, Any]] = None

    def reconcile_state(
        self,
        account_snapshot: Any,
        execution_history: List[CanonicalExecutionReport],
        current_positions: Dict[str, Any]
    ) -> Dict[str, Any]:
        discrepancies: List[str] = []

        # 1. Execution History Integrity (중복 exec_id 및 음수/무효 체결 탐지)
        seen_exec_ids: Set[str] = set()
        execution_ok = True
        total_exec_qty = 0
        calc_fees = 0.0

        for rep in execution_history:
            exec_id = getattr(rep, "exec_id", "")
            qty = getattr(rep, "executed_qty", 0)
            price = getattr(rep, "executed_price", 0.0)
            fee = getattr(rep, "fee", 0.0)

            if exec_id:
                if exec_id in seen_exec_ids:
                    execution_ok = False
                    discrepancies.append(f"Duplicate exec_id detected: {exec_id}")
                seen_exec_ids.add(exec_id)

            if qty <= 0:
                execution_ok = False
                discrepancies.append(f"Invalid non-positive executed_qty ({qty}) in exec {exec_id}")
            if price <= 0.0:
                execution_ok = False
                discrepancies.append(f"Invalid non-positive executed_price ({price}) in exec {exec_id}")
            if fee < 0.0:
                execution_ok = False
                discrepancies.append(f"Invalid negative fee ({fee}) in exec {exec_id}")

            if qty > 0 and fee >= 0.0:
                total_exec_qty += qty
                calc_fees += fee

        # 2. Replay Position & Realized PnL from Execution History using PositionManager
        replay_pm = PositionManager()
        expected_realized_pnl = 0.0
        for rep in execution_history:
            if getattr(rep, "executed_qty", 0) <= 0 or getattr(rep, "executed_price", 0.0) <= 0.0:
                continue
            symbol = rep.get_instrument_key() if hasattr(rep, "get_instrument_key") else getattr(rep, "symbol", "KOSPI200_OPTION")
            side_str = rep.side.value if hasattr(rep.side, "value") else str(rep.side)
            order_id = getattr(rep, "client_order_id", None)
            delta_pnl = replay_pm.update_position(
                symbol=symbol,
                side=side_str,
                qty=rep.executed_qty,
                price=rep.executed_price,
                multiplier=self.multiplier,
                client_order_id=order_id
            )
            expected_realized_pnl += delta_pnl

        # 3. Position Integrity Verification (수량, 방향, 평단가 일치 검증)
        position_ok = True
        replayed_positions = {k: v for k, v in replay_pm.positions.items() if v.get("qty", 0) > 0}
        actual_positions = {k: v for k, v in current_positions.items() if v.get("qty", 0) > 0}

        if set(replayed_positions.keys()) != set(actual_positions.keys()):
            position_ok = False
            discrepancies.append(
                f"Position symbols mismatch: replayed={set(replayed_positions.keys())} vs actual={set(actual_positions.keys())}"
            )
        else:
            for sym, exp_pos in replayed_positions.items():
                act_pos = actual_positions[sym]
                if exp_pos["qty"] != act_pos.get("qty"):
                    position_ok = False
                    discrepancies.append(f"Position qty mismatch for {sym}: expected {exp_pos['qty']} vs actual {act_pos.get('qty')}")
                if exp_pos["side"] != act_pos.get("side"):
                    position_ok = False
                    discrepancies.append(f"Position side mismatch for {sym}: expected {exp_pos['side']} vs actual {act_pos.get('side')}")
                if abs(exp_pos["avg_price"] - float(act_pos.get("avg_price", 0.0))) > 1e-4:
                    position_ok = False
                    discrepancies.append(
                        f"Position avg_price mismatch for {sym}: expected {exp_pos['avg_price']:.4f} vs actual {float(act_pos.get('avg_price', 0.0)):.4f}"
                    )

        # 4. Realized PnL Verification
        snap_realized = getattr(account_snapshot, "realized_pnl", 0.0)
        pnl_diff = abs(expected_realized_pnl - snap_realized)
        pnl_ok = pnl_diff < 1e-2
        if not pnl_ok:
            discrepancies.append(f"Realized PnL mismatch: replayed {expected_realized_pnl:.2f} vs snapshot {snap_realized:.2f}")

        # 5. Account Balance / Equity Verification (Initial Capital + Realized PnL + Unrealized PnL - Fees)
        balance_val = getattr(account_snapshot, "balance", getattr(account_snapshot, "total_balance", self.initial_capital))
        snap_unrealized = getattr(account_snapshot, "unrealized_pnl", 0.0)
        used_margin = getattr(account_snapshot, "used_margin", 0.0)
        free_margin = getattr(account_snapshot, "free_margin", 0.0)

        expected_balance = self.initial_capital + snap_realized + snap_unrealized - calc_fees
        balance_diff = abs(balance_val - expected_balance)
        balance_ok = balance_diff < 1e-2
        if not balance_ok:
            discrepancies.append(f"Account balance/equity mismatch: expected {expected_balance:.2f} vs actual {balance_val:.2f}")

        # 6. Margin Risk Integrity Audit
        expected_used_margin = self.margin_engine.calculate_used_margin(actual_positions, multiplier=self.multiplier)
        used_margin_diff = abs(expected_used_margin - used_margin)
        expected_free_margin = self.margin_engine.calculate_free_margin(balance_val, used_margin)
        free_margin_diff = abs(expected_free_margin - free_margin)

        margin_diff = max(used_margin_diff, free_margin_diff)
        margin_ok = margin_diff < 1e-2
        if not margin_ok:
            discrepancies.append(
                f"Margin mismatch: used_margin (exp={expected_used_margin:.2f}, act={used_margin:.2f}), "
                f"free_margin (exp={expected_free_margin:.2f}, act={free_margin:.2f})"
            )

        is_healthy = execution_ok and position_ok and pnl_ok and balance_ok and margin_ok

        report = {
            "is_healthy": is_healthy,
            "execution_ok": execution_ok,
            "balance_ok": balance_ok,
            "position_ok": position_ok,
            "pnl_ok": pnl_ok,
            "margin_ok": margin_ok,
            "balance_diff": round(balance_diff, 4),
            "pnl_diff": round(pnl_diff, 4),
            "margin_diff": round(margin_diff, 4),
            "total_executions": len(execution_history),
            "total_exec_qty": total_exec_qty,
            "calculated_fees": round(calc_fees, 2),
            "discrepancies": discrepancies,
        }

        self.last_report = report
        if not is_healthy:
            logger.error(f"[Reconciliation Audit FAIL] Discrepancies: {discrepancies}")

        return report

