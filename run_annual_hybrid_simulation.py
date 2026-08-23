"""
run_annual_hybrid_simulation.py

[Target Architecture Authoritative Main Execution Path]
Target Owner 서브시스템 전용 5년(625,000 Ticks) 실시간 하이브리드 백테스팅 주동 파이프라인
"""

import sys
import time
import orjson
import logging
from typing import Dict, Any

from shared.contracts.canonical import (
    CanonicalMarketTick,
    CanonicalOrderCommand,
    CanonicalExecutionReport,
    CanonicalAccountSnapshot
)
from virtual_market_simulator.runtime.simulator_runtime import VirtualMarketSimulatorRuntime
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime
from option_program.runtime.program_runtime import OptionProgramRuntime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def run_main_simulation(total_days: int = 1250, ticks_per_day: int = 500) -> Dict[str, Any]:
    print("=" * 80)
    print("[KOSPI200 BOT] Target Architecture 주동 5년 배속 실시간 가상 시뮬레이터 가동")
    print("=" * 80)
    print("  * 기반 아키텍처: Target Owner (VMS -> VSSF -> OptionProgram -> VSSF Matching)")
    print(f"  * 시뮬레이션 규모: {total_days} 영업일 / 약 {total_days * ticks_per_day:,} Ticks")
    print("=" * 80)

    # 1. Target Architecture Runtimes Initialization
    vms_runtime = VirtualMarketSimulatorRuntime()
    vssf_runtime = VirtualSecuritiesFirmRuntime(initial_capital=25000000.0)
    option_program_runtime = OptionProgramRuntime()

    start_time = time.time()
    total_ticks = 0
    total_executions = 0

    tick_generator = vms_runtime.generate_tick_stream(total_days=total_days, ticks_per_day=ticks_per_day)

    for tick in tick_generator:
        total_ticks += 1

        # Step 1: VMS Tick -> VSSF Market Gateway (Price Update & Valuation)
        vssf_runtime.process_market_data(tick)

        # Step 2: OptionProgram process_tick (Sensors -> Strategy Evaluation -> Order Commands)
        commands = option_program_runtime.process_tick(tick)

        # Step 3: Orders -> VSSF process_order (Risk Check -> OrderBook Matching -> Account Mutation -> ExecutionReport)
        for cmd in commands:
            report = vssf_runtime.process_order(cmd)
            if report:
                total_executions += 1
                # Step 4: ExecutionReport -> OptionProgram Consumer
                option_program_runtime.consume_execution_report(report)

        if total_ticks % (ticks_per_day * 125) == 0:
            pct = (total_ticks / (total_days * ticks_per_day)) * 100
            snapshot = vssf_runtime.get_account_snapshot()
            print(f"   [{pct:5.1f}%] {total_ticks:,} Ticks | Balance: KRW {snapshot.balance:,.0f} | Executions: {total_executions}")

    elapsed = time.time() - start_time
    final_snapshot = vssf_runtime.get_account_snapshot()
    tps = total_ticks / elapsed if elapsed > 0 else 0

    result_summary = {
        "status": "SUCCESS",
        "architecture": "Target_Authoritative_Owner",
        "total_ticks": total_ticks,
        "total_executions": total_executions,
        "elapsed_seconds": round(elapsed, 2),
        "ticks_per_second": round(tps, 1),
        "final_balance": final_snapshot.balance,
        "realized_pnl": final_snapshot.realized_pnl,
        "unrealized_pnl": final_snapshot.unrealized_pnl,
        "used_margin": final_snapshot.used_margin,
        "free_margin": final_snapshot.free_margin
    }

    print("=" * 80)
    print(f"[성공] Target Architecture 주동 {total_days}일({total_ticks:,} Ticks) 시뮬레이션 완수! (소요 시간: {elapsed:.2f}s)")
    print(f"  * 최종 자산: KRW {final_snapshot.balance:,.0f} | 총 체결 건수: {total_executions}")
    print("=" * 80)

    with open("annual_simulation_result.json", "wb") as f:
        f.write(orjson.dumps(result_summary))

    return result_summary

if __name__ == "__main__":
    run_main_simulation()
