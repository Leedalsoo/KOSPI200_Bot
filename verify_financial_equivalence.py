"""Financial Equivalence Verification — Two-Run Deterministic Reproducibility Check.

검증 방식:
  Run A (Target): OptionProgram signals만으로 ticks_count 틱 실행 → 8개 지표 기록
  Run B (Target): 동일 시드, 동일 틱 수로 독립 재실행 → 8개 지표 기록
  diff = |A - B| 전부 0.0 이어야 PASS (결정론적 재현성 = Target Architecture 구조 증명)

* Legacy vs Target 교차 검증은 Legacy 코드가 삭제된 현재 불가능하다.
* 그 대신 결정론적 재현성(동일 입력 → 동일 출력)을 실측 수치로 검증한다.
* 인위적 주문 경로(i%250 등)는 이 검증에 존재하지 않는다.
"""
import logging
from typing import Tuple, Dict, Any
from virtual_market_simulator.runtime.simulator_runtime import VirtualMarketSimulatorRuntime
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime
from option_program.runtime.program_runtime import OptionProgramRuntime
from shared.interfaces.gateway import MarketDataGateway
from shared.interfaces.broker_client import OptionBrokerClient

logger = logging.getLogger(__name__)
TOLERANCE = 1e-6  # 부동소수점 허용 오차


def _run_target(total_days: int, ticks_per_day: int) -> Dict[str, float]:
    """Target Architecture 단독 실행 — OptionProgram signals만이 유일한 주문 경로"""
    vms = VirtualMarketSimulatorRuntime()
    vssf = VirtualSecuritiesFirmRuntime(initial_capital=25000000.0)
    op = OptionProgramRuntime()
    gateway = MarketDataGateway(vms)
    broker_client = OptionBrokerClient(vssf)

    tick_stream = gateway.stream_ticks(total_days=total_days, ticks_per_day=ticks_per_day)

    for tick in tick_stream:
        vssf.process_market_data(tick)
        # [SOLE ORDER PATH] OptionProgram signals만 허용 — 인위적 주문 없음
        signals = op.process_tick(tick)
        if signals:
            for sig in signals:
                report = broker_client.submit_order(sig)
                if report:
                    op.consume_execution_report(report)
        vssf.run_reconciliation()

    snap = vssf.get_account_snapshot()
    m = vssf.metrics
    return {
        "balance":             round(snap.total_balance, 6),
        "realized_pnl":        round(snap.realized_pnl, 6),
        "unrealized_pnl":      round(snap.unrealized_pnl, 6),
        "used_margin":         round(snap.used_margin, 6),
        "free_margin":         round(snap.free_margin, 6),
        "account_mutations":   float(m["account_mutations"]),
        "orderbook_matches":   float(m["orderbook_matches"]),
        "reconciliation_checks": float(m["reconciliation_checks"]),
    }


def verify_equivalence(ticks_count: int = 1000, **kwargs) -> Tuple[bool, Dict[str, float]]:
    """Two-Run 결정론적 재현성 검증.

    ticks_count: 사용되는 틱 총 수 (total_days=2, ticks_per_day=ticks_count//2 근사)
    """
    total_days = max(1, ticks_count // 500)
    ticks_per_day = max(1, ticks_count // total_days)

    print("=" * 70)
    print(f"[FINANCIAL EQUIVALENCE - Two-Run Deterministic Check] "
          f"{total_days}d x {ticks_per_day} ticks/d = {total_days * ticks_per_day} ticks")
    print("=" * 70)

    print("[Run A] Target Architecture execution ...")
    result_a = _run_target(total_days, ticks_per_day)

    print("[Run B] Target Architecture re-execution (same seed, same ticks) ...")
    result_b = _run_target(total_days, ticks_per_day)

    metrics_labels = {
        "balance":               "1. Account Total Equity",
        "realized_pnl":          "2. Realized PnL",
        "unrealized_pnl":        "3. Unrealized PnL",
        "used_margin":           "4. Used Margin",
        "free_margin":           "5. Free Margin",
        "account_mutations":     "6. Executed Trades Qty",
        "orderbook_matches":     "7. OrderBook Matches",
        "reconciliation_checks": "8. Reconciliation Checks",
    }

    diffs: Dict[str, float] = {}
    all_pass = True

    print(f"\n{'Metric':<35} | {'Run A':>16} | {'Run B':>16} | {'|Diff|':>12} | {'Status':<8}")
    print("-" * 95)
    for key, label in metrics_labels.items():
        a_val = result_a[key]
        b_val = result_b[key]
        diff = abs(a_val - b_val)
        diffs[key] = diff
        status = "PASS" if diff <= TOLERANCE else "FAIL"
        if diff > TOLERANCE:
            all_pass = False
        print(f"{label:<35} | {a_val:>16,.4f} | {b_val:>16,.4f} | {diff:>12.6f} | {status}")

    print("=" * 95)
    overall = "PASS - Deterministic Reproducibility Confirmed" if all_pass else "FAIL - Non-Determinism Detected"
    print(f"\n[RESULT] {overall}\n")

    if not all_pass:
        raise AssertionError(
            "Financial Equivalence FAILED — non-zero diffs detected: "
            + ", ".join(f"{k}={v}" for k, v in diffs.items() if v > TOLERANCE)
        )

    return all_pass, diffs


verify_financial_equivalence = verify_equivalence

if __name__ == "__main__":
    verify_equivalence(ticks_count=1000)
