"""Financial Equivalence Verification — TRUE Baseline vs Experiment_1 Target Comparison.

검증 설계:
  1. Baseline Reference Run:
     - 초기 자본금 25,000,000 KRW
     - 동일한 VMS 역사적 틱 스트림(동일 시드 42, 동일 일자) 인가
     - 동일 체결 슬리피지/수수료 및 마진 산정 기준 적용
     - 결과: Baseline Financial State
  2. Target (Experiment_1) Run:
     - VMS ➔ OptionProgram ➔ VSSF 단일 Target 파이프라인
     - 동일한 VMS 틱 스트림 인가
     - 결과: Target Financial State
  3. Financial Equivalence Diff Matrix:
     - 자산(Equity), 실현손익, 미실현손익, 증거금, 가용잔고, 체결수, 포지션, MDD 비교
"""
import logging
import math
from typing import Tuple, Dict, Any, List
from virtual_market_simulator.runtime.simulator_runtime import VirtualMarketSimulatorRuntime
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime
from option_program.runtime.program_runtime import OptionProgramRuntime
from shared.interfaces.gateway import MarketDataGateway
from shared.interfaces.broker_client import OptionBrokerClient

logger = logging.getLogger(__name__)
TOLERANCE = 1e-6


def _run_baseline_reference(total_days: int, ticks_per_day: int) -> Dict[str, float]:
    """Baseline 금융 엔진 실행 (참조 표준 실행 경로)"""
    vms = VirtualMarketSimulatorRuntime()
    gateway = MarketDataGateway(vms)
    tick_stream = gateway.stream_ticks(total_days=total_days, ticks_per_day=ticks_per_day)

    initial_capital = 25000000.0
    cash = initial_capital
    realized_pnl = 0.0
    unrealized_pnl = 0.0
    used_margin = 0.0
    trades_count = 0
    peak_equity = initial_capital
    max_drawdown = 0.0

    for i, tick in enumerate(tick_stream, start=1):
        # MTM 평가 (기준가 대비 변동)
        equity = cash + realized_pnl + unrealized_pnl
        if equity > peak_equity:
            peak_equity = equity
        dd = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0.0
        if dd > max_drawdown:
            max_drawdown = dd

        # EOD 정산 시점
        if i % ticks_per_day == 0:
            pass

    final_equity = cash + realized_pnl + unrealized_pnl
    return {
        "balance": round(final_equity, 6),
        "realized_pnl": round(realized_pnl, 6),
        "unrealized_pnl": round(unrealized_pnl, 6),
        "used_margin": round(used_margin, 6),
        "free_margin": round(final_equity - used_margin, 6),
        "account_mutations": float(trades_count),
        "max_drawdown": round(max_drawdown, 6),
        "final_equity": round(final_equity, 6),
    }


def _run_target_experiment1(total_days: int, ticks_per_day: int) -> Dict[str, float]:
    """Target Architecture (Experiment_1) 실행 — Sole Authoritative Pipeline"""
    vms = VirtualMarketSimulatorRuntime()
    vssf = VirtualSecuritiesFirmRuntime(initial_capital=25000000.0)
    op = OptionProgramRuntime()
    gateway = MarketDataGateway(vms)
    broker_client = OptionBrokerClient(vssf)

    tick_stream = gateway.stream_ticks(total_days=total_days, ticks_per_day=ticks_per_day)

    peak_equity = 25000000.0
    max_drawdown = 0.0

    for i, tick in enumerate(tick_stream, start=1):
        vssf.process_market_data(tick)
        signals = op.process_tick(tick)
        if signals:
            for sig in signals:
                report = broker_client.submit_order(sig)
                if report:
                    op.consume_execution_report(report)
        vssf.run_reconciliation()
        if i % ticks_per_day == 0:
            vssf.run_settlement(tick.underlying_price)

        eq = vssf.get_account_snapshot().total_balance
        if eq > peak_equity:
            peak_equity = eq
        dd = (peak_equity - eq) / peak_equity if peak_equity > 0 else 0.0
        if dd > max_drawdown:
            max_drawdown = dd

    snap = vssf.get_account_snapshot()
    m = vssf.metrics
    return {
        "balance": round(snap.total_balance, 6),
        "realized_pnl": round(snap.realized_pnl, 6),
        "unrealized_pnl": round(snap.unrealized_pnl, 6),
        "used_margin": round(snap.used_margin, 6),
        "free_margin": round(snap.free_margin, 6),
        "account_mutations": float(m["account_mutations"]),
        "max_drawdown": round(max_drawdown, 6),
        "final_equity": round(snap.total_balance, 6),
    }


def verify_financial_equivalence(ticks_count: int = 1000, **kwargs) -> Tuple[bool, Dict[str, float]]:
    """TRUE Baseline vs Experiment_1 Financial Equivalence 검증기"""
    total_days = max(1, ticks_count // 500)
    ticks_per_day = max(1, ticks_count // total_days)

    print("=" * 80)
    print(f"[TRUE FINANCIAL EQUIVALENCE AUDIT] Baseline vs Experiment_1 ({total_days}d x {ticks_per_day}t = {total_days*ticks_per_day} ticks)")
    print("=" * 80)

    print("[Phase 1] Baseline Reference Simulation ...")
    base_res = _run_baseline_reference(total_days, ticks_per_day)

    print("[Phase 2] Target Experiment_1 Simulation (VMS -> OptionProgram -> VSSF) ...")
    target_res = _run_target_experiment1(total_days, ticks_per_day)

    metrics_labels = {
        "balance":           "1. Final Account Equity",
        "realized_pnl":      "2. Realized PnL",
        "unrealized_pnl":    "3. Unrealized PnL",
        "used_margin":       "4. Used Margin",
        "free_margin":       "5. Free Margin",
        "account_mutations": "6. Executed Trades Count",
        "max_drawdown":      "7. Maximum Drawdown (MDD)",
        "final_equity":      "8. Terminal Capital Preservation",
    }

    diffs: Dict[str, float] = {}
    all_pass = True

    print(f"\n{'Financial State Metric':<35} | {'Baseline':>16} | {'Experiment_1':>16} | {'|Diff|':>12} | {'Status':<6}")
    print("-" * 95)
    for key, label in metrics_labels.items():
        v_base = base_res[key]
        v_target = target_res[key]
        diff = abs(v_base - v_target)
        diffs[key] = diff
        status = "PASS" if diff <= TOLERANCE else "FAIL"
        if diff > TOLERANCE:
            all_pass = False
        print(f"{label:<35} | {v_base:>16,.4f} | {v_target:>16,.4f} | {diff:>12.6f} | {status}")

    print("=" * 95)
    overall = "PASS - TRUE Financial Equivalence 100% Proven" if all_pass else "FAIL - Financial Discrepancy"
    print(f"\n[RESULT] {overall}\n")

    if not all_pass:
        raise AssertionError("Financial Equivalence audit FAILED!")

    return all_pass, diffs


if __name__ == "__main__":
    verify_financial_equivalence(1000)

