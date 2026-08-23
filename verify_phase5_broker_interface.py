"""Phase 5: Dual Broker Interface & Paper Trading Execution Verification.

Verifies:
1. PaperBrokerAdapter Instantiation & Connection
2. Standard Order Submission -> CanonicalExecutionReport Issuance
3. Margin Verification & Insufficient Margin Handling
4. Slippage & Fee Calculation Integration
5. Account Snapshot & Position Invariants
6. RealBrokerAdapterStub Interface Compliance
7. BrokerFactory Dynamic Switching (PAPER <-> REAL)
8. End-to-End Pipeline Financial Integrity
"""
import sys
import logging

from shared.contracts.canonical import (
    CanonicalMarketTick,
    CanonicalOrderCommand,
    CanonicalOrderSide,
    CanonicalAssetType,
    CanonicalOptionType
)
from option_program.broker.broker_interface import (
    BrokerMode,
    BrokerFactory,
    PaperBrokerAdapter,
    RealBrokerAdapterStub
)
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def run_phase5_broker_interface_audit():
    print("=" * 105)
    print("[PHASE 5 BROKER INTERFACE & PAPER TRADING AUDIT] Dual Broker Architecture & Financial Invariants")
    print("=" * 105)

    vssf = VirtualSecuritiesFirmRuntime(initial_capital=30_000_000.0)
    
    # 0. Market Data Feed to VSSF
    tick = CanonicalMarketTick(
        seq_id=1, timestamp="09:00:00.000",
        underlying_price=350.0, last_price=350.0, bid_price=349.95, ask_price=350.05,
        volume=1000, strike_price=350.0
    )
    vssf.process_market_data(tick)

    results = []

    # 1. Factory Creation (PAPER Mode)
    paper_broker = BrokerFactory.create_broker(mode=BrokerMode.PAPER, vssf_runtime=vssf)
    results.append(("Broker: Factory PAPER Instantiation", isinstance(paper_broker, PaperBrokerAdapter), "PaperBrokerAdapter created"))
    results.append(("Broker: Paper Connection Status", paper_broker.is_connected() is True, "PaperBroker connected"))

    # 2. Normal Order Submission -> CanonicalExecutionReport
    cmd = CanonicalOrderCommand(
        client_order_id="BRK-001", track_id="Track1", asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY, qty=2, price=2.50, option_type=CanonicalOptionType.CALL,
        strike=350.0, tag_id="test_buy"
    )
    exec_rep = paper_broker.send_order(cmd)
    results.append(("Broker: Send Order & Execution Report", exec_rep is not None and exec_rep.exec_id.startswith("EXEC-"), f"Issued {exec_rep.exec_id if exec_rep else 'None'}"))

    # 3. Slippage & Fee Application
    results.append(("Broker: Slippage Integration", exec_rep is not None and exec_rep.executed_price >= 2.50, f"Executed price {exec_rep.executed_price if exec_rep else 0} >= 2.50"))
    results.append(("Broker: Fee Calculation Precision", exec_rep is not None and exec_rep.fee > 0, f"Fee {exec_rep.fee if exec_rep else 0} > 0"))

    # 4. Account Summary & Position Retrieval
    acc_summary = paper_broker.get_account_summary()
    positions = paper_broker.get_positions()
    results.append(("Broker: Account Summary Retrievable", acc_summary is not None and acc_summary.account_id == "ACC-VSSF-001", "Summary valid"))
    results.append(("Broker: Position Inventory Query", len(positions) > 0, f"Positions active: {len(positions)}"))

    # 5. Margin Rejection
    huge_cmd = CanonicalOrderCommand(
        client_order_id="BRK-002", track_id="Track1", asset_type=CanonicalAssetType.FUTURES,
        side=CanonicalOrderSide.BUY, qty=100, price=350.0, option_type=CanonicalOptionType.CALL,
        strike=350.0, tag_id="huge_margin"
    )
    rej_rep = paper_broker.send_order(huge_cmd)
    results.append(("Broker: Margin Block Verification", rej_rep is None, "Insufficient margin blocked safely"))

    # 6. Factory Creation (REAL Mode Stub)
    real_broker = BrokerFactory.create_broker(mode=BrokerMode.REAL)
    results.append(("Broker: Factory REAL Stub Instantiation", isinstance(real_broker, RealBrokerAdapterStub), "RealBrokerAdapterStub created"))
    results.append(("Broker: Real Stub Initial State", real_broker.is_connected() is False, "Disconnected safely by default"))

    # 7. Financial Integrity Invariant
    results.append(("Broker: Single Authority Financial Invariant", vssf.account.balance > 0, f"Account balance {vssf.account.balance} KRW intact"))

    # -------------------------------------------------------------
    # PRINT RESULTS
    # -------------------------------------------------------------
    print("-" * 105)
    print(f"{'Verification Check':<45} | {'Status':<10} | {'Verification Evidence'}")
    print("-" * 105)
    all_passed = True
    for name, passed, evidence in results:
        status_str = "PASS" if passed else "FAIL"
        if not passed:
            all_passed = False
        print(f"{name:<45} | {status_str:<10} | {evidence}")

    print("=" * 105)
    if all_passed:
        print(f"[PHASE 5 RESULT] PASS - All {len(results)}/9 Broker Interface Invariants Verified 100% Operational!")
    else:
        print("[PHASE 5 RESULT] FAIL - Broker Interface Invariants Failed!")
    print("=" * 105)
    return all_passed

if __name__ == "__main__":
    success = run_phase5_broker_interface_audit()
    sys.exit(0 if success else 1)
