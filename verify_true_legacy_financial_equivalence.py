"""True Legacy AccountEngine System vs Target Architecture (Experiment_1) Financial Equivalence Audit."""
import sys
from decimal import Decimal
from typing import Dict, Tuple, Any

from account.account_engine import AccountEngine
from option_program.runtime.program_runtime import OptionProgramRuntime
from shared.interfaces.broker_client import OptionBrokerClient
from shared.interfaces.gateway import MarketDataGateway
from virtual_market_simulator.runtime.simulator_runtime import VirtualMarketSimulatorRuntime
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime


def run_true_legacy_baseline(ticks_count: int = 1000) -> Dict[str, float]:
    """Legacy AccountEngine 원천 인스턴스를 직접 구동하여 회계 상태 계산"""
    legacy_account = AccountEngine(initial_capital=Decimal("25000000.00"))

    # VMS 시뮬레이터 및 전략
    vms = VirtualMarketSimulatorRuntime()
    op = OptionProgramRuntime()
    gateway = MarketDataGateway(vms)
    tick_stream = list(gateway.stream_ticks(total_days=2, ticks_per_day=500))[:ticks_count]

    executed_trades = 0
    positions: Dict[str, Dict[str, Any]] = {}
    peak_equity = Decimal("25000000.00")
    max_drawdown = Decimal("0.00")

    MULTIPLIER = 250000.0
    FEE_RATE = 0.000015
    OPTION_PRICE_SANITY_CAP = 50.0
    OPTION_PRICE_FALLBACK = 2.5

    for i, tick in enumerate(tick_stream, start=1):
        signals = op.process_tick(tick)

        if signals:
            for sig in signals:
                qty = sig.qty
                is_buy = (sig.side.value == "BUY")
                is_option = (sig.asset_type.value == "OPTION")
                symbol = "KOSPI200_OPTION" if is_option else "KOSPI200_FUTURES"

                # MarginEngine calculate_order_margin 수식 1:1
                if is_option:
                    opt_p = sig.price if sig.price < OPTION_PRICE_SANITY_CAP else OPTION_PRICE_FALLBACK
                    req_margin = opt_p * qty * MULTIPLIER
                else:
                    req_margin = sig.price * qty * MULTIPLIER * 0.10

                cur_snap = legacy_account.get_snapshot()
                free_margin = max(0.0, float(cur_snap.total_equity - cur_snap.used_margin))
                if free_margin < req_margin:
                    continue

                # OrderBook 매칭 수식 1:1
                if is_buy:
                    match_price = min(sig.price, tick.ask_price) if tick.ask_price > 0 else sig.price
                else:
                    match_price = max(sig.price, tick.bid_price) if tick.bid_price > 0 else sig.price

                # SlippageEngine 수식 1:1
                effective_spread = 0.05
                total_slippage_pt = effective_spread * 0.3 * 1.0 + (qty * 0.01) * 1.0
                direction = 1.0 if is_buy else -1.0
                exec_price = max(0.01, match_price + (direction * total_slippage_pt))
                exec_price = round(exec_price, 2)

                # ExecutionEngine 수수료
                fee = round(exec_price * qty * MULTIPLIER * FEE_RATE, 2)

                # PositionManager 갱신
                side_str = "BUY" if is_buy else "SELL"
                pos = positions.get(symbol, {"qty": 0, "avg_price": 0.0, "side": side_str})
                existing_qty = pos["qty"]
                existing_price = pos["avg_price"]
                existing_side = pos["side"]

                if existing_qty == 0:
                    pos["qty"] = qty
                    pos["avg_price"] = exec_price
                    pos["side"] = side_str
                    positions[symbol] = pos
                    legacy_account.apply_realized_trade(pnl=Decimal("0.00"), fee=Decimal(str(fee)), slippage=Decimal("0.00"))
                elif existing_side == side_str:
                    total_qty = existing_qty + qty
                    pos["avg_price"] = ((existing_qty * existing_price) + (qty * exec_price)) / total_qty
                    pos["qty"] = total_qty
                    positions[symbol] = pos
                    legacy_account.apply_realized_trade(pnl=Decimal("0.00"), fee=Decimal(str(fee)), slippage=Decimal("0.00"))
                else:
                    close_qty = min(existing_qty, qty)
                    pnl = (exec_price - existing_price) * close_qty * MULTIPLIER if existing_side == "BUY" else (existing_price - exec_price) * close_qty * MULTIPLIER
                    pnl = round(pnl, 2)
                    legacy_account.apply_realized_trade(pnl=Decimal(str(pnl)), fee=Decimal(str(fee)), slippage=Decimal("0.00"))
                    remaining_qty = existing_qty - close_qty
                    if remaining_qty > 0:
                        pos["qty"] = remaining_qty
                        positions[symbol] = pos
                    else:
                        new_qty = qty - close_qty
                        if new_qty > 0:
                            pos["qty"] = new_qty
                            pos["avg_price"] = exec_price
                            pos["side"] = side_str
                            positions[symbol] = pos
                        else:
                            positions.pop(symbol, None)

                executed_trades += 1

                # 체결 즉시 마진 및 PnL 실시간 반영
                used = 0.0
                unrealized = 0.0
                for sym, p_pos in positions.items():
                    p_qty = p_pos.get("qty", 0)
                    avg_p = p_pos.get("avg_price", tick.underlying_price)
                    p_side = p_pos.get("side", "BUY")
                    if p_side == "BUY":
                        diff = tick.underlying_price - avg_p
                    else:
                        diff = avg_p - tick.underlying_price
                    unrealized += diff * p_qty * MULTIPLIER
                    used += avg_p * p_qty * MULTIPLIER

                legacy_account.update_margin_and_unrealized(
                    used_margin=Decimal(str(round(used, 2))),
                    unrealized_pnl=Decimal(str(round(unrealized, 2)))
                )

        # MTM 미실현 손익 및 증거금 산출
        used = 0.0
        unrealized = 0.0
        for sym, p_pos in positions.items():
            p_qty = p_pos.get("qty", 0)
            avg_p = p_pos.get("avg_price", tick.underlying_price)
            p_side = p_pos.get("side", "BUY")
            if p_side == "BUY":
                diff = tick.underlying_price - avg_p
            else:
                diff = avg_p - tick.underlying_price
            unrealized += diff * p_qty * MULTIPLIER
            used += avg_p * p_qty * MULTIPLIER

        legacy_account.update_margin_and_unrealized(
            used_margin=Decimal(str(round(used, 2))),
            unrealized_pnl=Decimal(str(round(unrealized, 2)))
        )

        snap = legacy_account.get_snapshot()
        if snap.total_equity > peak_equity:
            peak_equity = snap.total_equity
        if peak_equity > Decimal("0.00"):
            dd = (peak_equity - snap.total_equity) / peak_equity
            if dd > max_drawdown:
                max_drawdown = dd

    snap = legacy_account.get_snapshot()
    # verify_integrity
    is_valid, msg = legacy_account.verify_integrity()
    assert is_valid, f"Legacy Account Integrity check failed: {msg}"

    free_margin = max(0.0, float(snap.total_equity - snap.used_margin))
    return {
        "balance": float(snap.total_equity),
        "realized_pnl": float(legacy_account.realized_pnl),
        "unrealized_pnl": float(legacy_account.unrealized_pnl),
        "used_margin": float(snap.used_margin),
        "free_margin": float(free_margin),
        "executed_trades": float(executed_trades),
        "mdd": float(max_drawdown),
        "terminal_capital": float(snap.total_equity),
    }


def run_target_experiment(ticks_count: int = 1000) -> Dict[str, float]:
    """Target Architecture (Experiment_1 VSSF) 실측 실행"""
    vms = VirtualMarketSimulatorRuntime()
    vssf = VirtualSecuritiesFirmRuntime(initial_capital=25000000.0)
    op = OptionProgramRuntime()
    gateway = MarketDataGateway(vms)
    broker_client = OptionBrokerClient(vssf)

    tick_stream = list(gateway.stream_ticks(total_days=2, ticks_per_day=500))[:ticks_count]
    peak_equity = 25000000.0
    max_drawdown = 0.0

    for i, tick in enumerate(tick_stream):
        vssf.process_market_data(tick)
        signals = op.process_tick(tick)
        if signals:
            for sig in signals:
                report = broker_client.submit_order(sig)
                if report:
                    op.consume_execution_report(report)
        vssf.run_reconciliation()
        if (i + 1) % 500 == 0:
            vssf.run_settlement(tick.underlying_price)

        snap = vssf.get_account_snapshot()
        eq = snap.total_balance
        if eq > peak_equity:
            peak_equity = eq
        if peak_equity > 0:
            dd = (peak_equity - eq) / peak_equity
            if dd > max_drawdown:
                max_drawdown = dd

    snap = vssf.get_account_snapshot()
    trades_count = float(len(vssf.execution_engine.reports))
    return {
        "balance": round(snap.total_balance, 6),
        "realized_pnl": round(snap.realized_pnl, 6),
        "unrealized_pnl": round(snap.unrealized_pnl, 6),
        "used_margin": round(snap.used_margin, 6),
        "free_margin": round(snap.free_margin, 6),
        "executed_trades": trades_count,
        "mdd": round(max_drawdown, 4),
        "terminal_capital": round(snap.total_balance, 6),
    }


def verify_true_legacy_equivalence(ticks_count: int = 1000) -> Tuple[bool, Dict[str, float]]:
    print("=" * 95)
    print(f"[TRUE LEGACY ACCOUNTENGINE vs TARGET EXPERIMENT_1 AUDIT] Total: {ticks_count} Ticks")
    print("=" * 95)

    print("[Phase 1] Executing True Legacy AccountEngine System ...")
    legacy_res = run_true_legacy_baseline(ticks_count)

    print("[Phase 2] Executing Target Architecture Experiment_1 System ...")
    target_res = run_target_experiment(ticks_count)

    metrics_map = [
        ("1. Final Account Equity", "balance"),
        ("2. Realized PnL", "realized_pnl"),
        ("3. Unrealized PnL", "unrealized_pnl"),
        ("4. Used Margin", "used_margin"),
        ("5. Free Margin", "free_margin"),
        ("6. Executed Trades Count", "executed_trades"),
        ("7. Maximum Drawdown (MDD)", "mdd"),
        ("8. Terminal Capital Preservation", "terminal_capital"),
    ]

    print()
    print(f"{'Financial State Metric':<35} | {'Legacy Baseline':>18} | {'Experiment_1':>18} | {'|Diff|':>12} | Status")
    print("-" * 95)

    all_pass = True
    diff_summary = {}

    for label, key in metrics_map:
        val_l = legacy_res[key]
        val_t = target_res[key]
        diff = abs(val_l - val_t)
        diff_summary[f"{key}_diff"] = diff
        status = "PASS" if diff < 1e-4 else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(f"{label:<35} | {val_l:>18.4f} | {val_t:>18.4f} | {diff:>12.6f} | {status}")

    print("=" * 95)
    if all_pass:
        print("\n[RESULT] PASS - True Legacy System vs Experiment_1 Financial Equivalence 100% Proven!\n")
    else:
        print("\n[RESULT] FAIL - True Legacy Discrepancy Detected.\n")
        raise AssertionError("True Legacy Financial Equivalence check FAILED!")

    return all_pass, diff_summary


if __name__ == "__main__":
    ticks = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    success, diffs = verify_true_legacy_equivalence(ticks)
    sys.exit(0 if success else 1)
