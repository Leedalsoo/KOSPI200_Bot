"""Comprehensive End-to-End Test for the Entire Integrated Trading Pipeline.

Verifies the complete closed-loop call chain:
VMS Market Data
-> Feature/Sensor
-> Strategy Track 1~9
-> SignalGenerator
-> DecisionArbiter
-> RiskSensor/RiskEngine
-> RiskGate (RiskApprovalToken issuance)
-> Portfolio/Position
-> Order FSM (OmsFsm) & OrderRouter
-> Virtual Broker Adapter (PaperBrokerAdapter)
-> Virtual Securities Firm Runtime (VSSF)
-> ExecutionEngine & 3-Factor Slippage
-> Account / Position / LedgerEngine
-> Reconciliation / Settlement
-> UI / Telemetry
"""
import pytest
import asyncio
from typing import Dict, Any

from shared.contracts.canonical import (
    CanonicalMarketTick,
    CanonicalOrderCommand,
    CanonicalExecutionReport,
    CanonicalAssetType,
    CanonicalOrderSide,
    CanonicalOptionType
)
from virtual_market_simulator.runtime.simulator_runtime import VirtualMarketSimulatorRuntime
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime
from option_program.broker.broker_interface import BrokerFactory, BrokerMode, PaperBrokerAdapter
from option_program.runtime.program_runtime import OptionProgramRuntime
from main import TradingSystem
from shared.core.contracts import OrderStatus


def test_full_pipeline_end_to_end_closed_loop():
    """1. Validates full closed-loop pipeline execution from VMS to Ledger & Reconciliation."""
    # 1. Initialize VMS & VSSF
    vms = VirtualMarketSimulatorRuntime()
    vssf = VirtualSecuritiesFirmRuntime(initial_capital=50_000_000.0)
    broker = BrokerFactory.create_broker(mode=BrokerMode.PAPER, vssf_runtime=vssf)
    op = OptionProgramRuntime(account_summary=vssf.get_account_snapshot())

    # 2. Process a series of ticks from VMS
    tick_gen = vms.generate_tick_stream(total_days=1, ticks_per_day=50)
    
    total_orders_generated = 0
    total_executions_handled = 0

    for tick in tick_gen:
        # Step 1: VSSF receives market data
        vssf.process_market_data(tick)

        # Step 2: OptionProgram synchronizes account snapshot (Read-Only)
        op.update_account_summary(vssf.get_account_snapshot())

        # Step 3: OptionProgram processes tick through full pipeline
        # (Sensor -> Track1~9 -> SignalGenerator -> DecisionArbiter -> RiskGate -> FSM)
        commands = op.process_tick(tick)

        if commands:
            for cmd in commands:
                total_orders_generated += 1
                
                # Check that command went through FSM & has a valid mapped order_uuid
                order_uuid = op._order_id_to_uuid.get(cmd.client_order_id)
                assert order_uuid is not None
                fsm_status = op.oms_fsm.get_status(order_uuid)
                assert fsm_status in (OrderStatus.VALIDATED, OrderStatus.SENT)

                # Step 4: Broker routing (주문 접수 ACK 확보)
                ack = broker.send_order(cmd)
                if ack is not None:
                    assert ack.success is True
                    assert ack.broker_order_id.startswith("BRK-PAPER-")

            # Step 5: Separate Execution Polling & Consumption
            exec_reports = broker.poll_execution_reports()
            for rep in exec_reports:
                total_executions_handled += 1
                assert rep.executed_qty > 0
                assert rep.exec_id.startswith("EXEC-")
                
                # OptionProgram consumes execution report & completes FSM
                op.consume_execution_report(rep)
                cmd_uuid = op._order_id_to_uuid.get(rep.client_order_id)
                if cmd_uuid:
                    final_status = op.oms_fsm.get_status(cmd_uuid)
                    assert final_status == OrderStatus.FILLED

    # Step 6: Verify VSSF Account, Position, and Ledger integrity
    assert vssf.account.balance > 0
    assert len(vssf.account.ledger_engine.transactions) > 0
    assert total_orders_generated > 0
    assert total_executions_handled > 0

    # Step 7: EOD Settlement & Authoritative Reconciliation
    settle_rec = vssf.run_settlement(final_settlement_price=350.0)
    assert settle_rec["type"] == "EOD"

    rec_res = vssf.run_reconciliation()
    assert rec_res["is_healthy"] is True
    assert rec_res["balance_ok"] is True


def test_main_trading_system_pipeline_async():
    """2. Validates that main.py TradingSystem successfully orchestrates the entire pipeline."""
    async def _run():
        config = {"broker_mode": "PAPER", "initial_capital": 50_000_000.0}
        system = TradingSystem(config)
        await system.initialize()
        
        assert system.vms is not None
        assert system.vssf is not None
        assert system.broker is not None
        assert system.op_runtime is not None

        await system.run_loop(max_ticks=20)
        
        assert system.ticks_processed == 20
        assert system.orders_routed > 0
        assert system.executions_handled > 0
        
        # Verify reconciliation health
        rec = system.vssf.run_reconciliation()
        assert rec.get("is_healthy") is True

        await system.shutdown()

    asyncio.run(_run())


def test_signal_generator_to_arbiter_to_risk_gate_chain():
    """3. Strictly tests that SignalGenerator -> DecisionArbiter -> RiskGate -> FSM call chain is active."""
    op = OptionProgramRuntime()
    tick = CanonicalMarketTick(
        timestamp="09:00:01",
        underlying_price=350.0,
        strike_price=350.0,
        option_type="CALL",
        bid_price=2.45,
        ask_price=2.55,
        last_price=2.50,
        volume=100,
        seq_id=1
    )

    # Calling process_tick executes the full pipeline
    commands = op.process_tick(tick)
    assert len(commands) > 0

    for cmd in commands:
        # 1. Check client order id format generated by pipeline
        assert cmd.client_order_id.startswith("ORD-T1-")
        
        # 2. Check FSM registered
        order_uuid = op._order_id_to_uuid.get(cmd.client_order_id)
        assert order_uuid is not None
        assert op.oms_fsm.get_status(order_uuid) == OrderStatus.SENT
