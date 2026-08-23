"""State Recovery Determinism & Reconciliation Verification.

검증 흐름:
  1. Base Run (연속 1000틱): 틱 1~1000 단일 런타임으로 실행 -> State A
  2. Recovery Run (스냅샷 & 복구 1000틱):
     - 틱 1~500 실행 -> create_recovery_snapshot()
     - 런타임 종료 및 New Runtime 생성 (재시작 모사)
     - restore_recovery_snapshot()으로 복구
     - 틱 501~1000 잔여 실행 -> State B
  3. Diff = |State A - State B| 전부 0.000000 이어야 PASS (Recovery 완벽 증명)
"""
from typing import Dict, Tuple
from virtual_market_simulator.runtime.simulator_runtime import VirtualMarketSimulatorRuntime
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime
from option_program.runtime.program_runtime import OptionProgramRuntime
from shared.interfaces.gateway import MarketDataGateway
from shared.interfaces.broker_client import OptionBrokerClient

TOLERANCE = 1e-6


def run_continuous(total_days: int = 2, ticks_per_day: int = 500) -> Dict[str, float]:
    """단일 연속 실행 (Base Run)"""
    vms = VirtualMarketSimulatorRuntime()
    vssf = VirtualSecuritiesFirmRuntime(initial_capital=25000000.0)
    op = OptionProgramRuntime()
    gateway = MarketDataGateway(vms)
    broker_client = OptionBrokerClient(vssf)

    tick_stream = gateway.stream_ticks(total_days=total_days, ticks_per_day=ticks_per_day)

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

    snap = vssf.get_account_snapshot()
    m = vssf.metrics
    ledger_count = len(getattr(vssf.account.ledger_engine, "transactions", []))
    return {
        "balance": round(snap.total_balance, 6),
        "realized_pnl": round(snap.realized_pnl, 6),
        "unrealized_pnl": round(snap.unrealized_pnl, 6),
        "used_margin": round(snap.used_margin, 6),
        "free_margin": round(snap.free_margin, 6),
        "account_mutations": float(m["account_mutations"]),
        "orderbook_matches": float(m["orderbook_matches"]),
        "reconciliation_checks": float(m["reconciliation_checks"]),
        "ledger_entries": float(ledger_count),
    }


def run_with_recovery(total_days: int = 2, ticks_per_day: int = 500, snapshot_tick: int = 500) -> Dict[str, float]:
    """스냅샷 생성 및 새 런타임 복구 후 잔여 틱 실행 (Recovery Run)"""
    vms = VirtualMarketSimulatorRuntime()
    vssf = VirtualSecuritiesFirmRuntime(initial_capital=25000000.0)
    op = OptionProgramRuntime()
    gateway = MarketDataGateway(vms)
    broker_client = OptionBrokerClient(vssf)

    tick_stream = list(gateway.stream_ticks(total_days=total_days, ticks_per_day=ticks_per_day))

    # Phase 1: 1 ~ snapshot_tick 실행
    for i in range(snapshot_tick):
        tick = tick_stream[i]
        vssf.process_market_data(tick)
        signals = op.process_tick(tick)
        if signals:
            for sig in signals:
                report = broker_client.submit_order(sig)
                if report:
                    op.consume_execution_report(report)
        vssf.run_reconciliation()
        if (i + 1) % ticks_per_day == 0:
            vssf.run_settlement(tick.underlying_price)

    # State Snapshot 저장
    saved_snapshot = vssf.create_recovery_snapshot(sequence_id=snapshot_tick)
    phase1_reconciliation = vssf.metrics["reconciliation_checks"]

    # Phase 2: 새 런타임 생성 (Process Restart 모사) 및 State 복구
    vssf_new = VirtualSecuritiesFirmRuntime(initial_capital=25000000.0)
    vssf_new.restore_recovery_snapshot(saved_snapshot)
    broker_client_new = OptionBrokerClient(vssf_new)

    # Phase 3: snapshot_tick ~ 마지막 틱까지 잔여 실행
    for i in range(snapshot_tick, len(tick_stream)):
        tick = tick_stream[i]
        vssf_new.process_market_data(tick)
        signals = op.process_tick(tick)
        if signals:
            for sig in signals:
                report = broker_client_new.submit_order(sig)
                if report:
                    op.consume_execution_report(report)
        vssf_new.run_reconciliation()
        if (i + 1) % ticks_per_day == 0:
            vssf_new.run_settlement(tick.underlying_price)

    snap = vssf_new.get_account_snapshot()
    m = vssf_new.metrics
    ledger_count_new = len(getattr(vssf_new.account.ledger_engine, "transactions", []))
    return {
        "balance": round(snap.total_balance, 6),
        "realized_pnl": round(snap.realized_pnl, 6),
        "unrealized_pnl": round(snap.unrealized_pnl, 6),
        "used_margin": round(snap.used_margin, 6),
        "free_margin": round(snap.free_margin, 6),
        "account_mutations": float(m["account_mutations"]),
        "orderbook_matches": float(m["orderbook_matches"]),
        "reconciliation_checks": float(m["reconciliation_checks"]),
        "ledger_entries": float(ledger_count_new),
    }


def verify_recovery_determinism(ticks_count: int = 1000) -> Tuple[bool, Dict[str, float]]:
    print("=" * 75)
    print(f"[RECOVERY DETERMINISM & RECONCILIATION AUDIT] Total: {ticks_count} Ticks")
    print("=" * 75)

    print("[Phase 1] Continuous Base Execution (1000 ticks) ...")
    base_res = run_continuous(total_days=2, ticks_per_day=500)

    print("[Phase 2] Recovery Execution (500 ticks -> Snapshot -> Restart -> 500 ticks) ...")
    rec_res = run_with_recovery(total_days=2, ticks_per_day=500, snapshot_tick=500)

    labels = {
        "balance": "1. Account Total Equity",
        "realized_pnl": "2. Realized PnL",
        "unrealized_pnl": "3. Unrealized PnL",
        "used_margin": "4. Used Margin",
        "free_margin": "5. Free Margin",
        "account_mutations": "6. Executed Trades Qty",
        "orderbook_matches": "7. OrderBook Matches",
        "reconciliation_checks": "8. Reconciliation Checks (Cumulative)",
        "ledger_entries": "9. Authoritative Ledger Entries",
    }

    diffs: Dict[str, float] = {}
    all_pass = True

    print(f"\n{'Financial State Metric':<35} | {'Base (Continuous)':>18} | {'Recovered (Restart)':>18} | {'|Diff|':>10} | {'Status':<6}")
    print("-" * 97)

    for k, label in labels.items():
        v_base = base_res[k]
        v_rec = rec_res[k]
        diff = abs(v_base - v_rec)
        diffs[k] = diff
        status = "PASS" if diff <= TOLERANCE else "FAIL"
        if diff > TOLERANCE:
            all_pass = False
        print(f"{label:<35} | {v_base:>18,.4f} | {v_rec:>18,.4f} | {diff:>10.6f} | {status}")

    print("=" * 97)
    overall = "PASS - Recovery Determinism & Reconciliation 100% Proven" if all_pass else "FAIL - State Mismatch"
    print(f"\n[RESULT] {overall}\n")

    if not all_pass:
        raise AssertionError("State Recovery Determinism check FAILED!")

    return all_pass, diffs



if __name__ == "__main__":
    verify_recovery_determinism(1000)

