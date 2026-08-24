"""Unit Test: Risk Sensor, Risk Engine & Pre-Trade Risk Gate Pipeline."""
import pytest
from datetime import datetime

from shared.contracts.canonical import (
    CanonicalOrderCommand,
    CanonicalAccountSummary,
    CanonicalOrderSide,
    CanonicalAssetType,
    CanonicalOptionType
)
from shared.core.contracts import RiskApprovalToken
from option_program.risk_control.risk_engine import (
    RiskConfig,
    RiskEngine,
    RiskGate
)
from virtual_securities_firm.margin.margin_engine import MarginEngine

def create_sample_account(total_balance: float = 50_000_000.0, free_margin: float = 50_000_000.0) -> CanonicalAccountSummary:
    return CanonicalAccountSummary(
        account_id="ACC-TEST-001",
        total_balance=total_balance,
        used_margin=total_balance - free_margin,
        free_margin=free_margin,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

def test_risk_gate_normal_admission():
    """Validates that a normal risk-compliant order receives a valid RiskApprovalToken."""
    config = RiskConfig(max_order_qty=50)
    gate = RiskGate(RiskEngine(config=config))
    account = create_sample_account(total_balance=50_000_000.0, free_margin=50_000_000.0)

    cmd = CanonicalOrderCommand(
        client_order_id="RISK-OK-001",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=2,
        price=2.50,
        option_type=CanonicalOptionType.CALL,
        strike=350.0,
        tag_id="test"
    )
    approved, token, reason = gate.admit_order(cmd, account)
    assert approved is True
    assert token is not None
    assert reason is None
    assert isinstance(token, RiskApprovalToken)
    assert token.signature.startswith("SIG-RISK-APPROVED-Track1")

def test_risk_gate_excessive_margin_rejection():
    """Validates that an order requiring more margin than free_margin is rejected."""
    gate = RiskGate()
    # Free margin only 1,000,000 KRW
    account = create_sample_account(total_balance=50_000_000.0, free_margin=1_000_000.0)

    # 10 contracts of 350.0 Futures -> req margin = 350 * 10 * 250,000 * 0.10 = 87,500,000 KRW
    cmd = CanonicalOrderCommand(
        client_order_id="RISK-MARGIN-001",
        track_id="Track2",
        asset_type=CanonicalAssetType.FUTURES,
        side=CanonicalOrderSide.BUY,
        qty=10,
        price=350.0,
        option_type=CanonicalOptionType.CALL,
        strike=350.0,
        tag_id="margin"
    )
    approved, token, reason = gate.admit_order(cmd, account)
    assert approved is False
    assert token is None
    assert "INSUFFICIENT_FREE_MARGIN" in reason

def test_risk_gate_order_qty_limit():
    """Validates that orders exceeding max_order_qty threshold are rejected."""
    config = RiskConfig(max_order_qty=20)
    gate = RiskGate(RiskEngine(config=config))
    account = create_sample_account()

    cmd = CanonicalOrderCommand(
        client_order_id="RISK-QTY-001",
        track_id="Track3",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=50,  # Exceeds 20
        price=2.0,
        option_type=CanonicalOptionType.CALL,
        strike=350.0,
        tag_id="qty"
    )
    approved, token, reason = gate.admit_order(cmd, account)
    assert approved is False
    assert "EXCEEDED_MAX_ORDER_QTY" in reason

def test_risk_gate_daily_loss_limit():
    """Validates that orders are blocked when daily realized losses breach the daily threshold."""
    config = RiskConfig(max_daily_loss_krw=5_000_000.0)
    engine = RiskEngine(config=config)
    gate = RiskGate(engine)
    account = create_sample_account()

    # Simulate accumulated daily loss of 6M KRW
    engine.record_realized_loss(-6_000_000.0)

    cmd = CanonicalOrderCommand(
        client_order_id="RISK-LOSS-001",
        track_id="Track4",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=1,
        price=2.0,
        option_type=CanonicalOptionType.CALL,
        strike=350.0,
        tag_id="loss"
    )
    approved, token, reason = gate.admit_order(cmd, account)
    assert approved is False
    assert "EXCEEDED_MAX_DAILY_LOSS" in reason

def test_risk_gate_kill_switch_immediate_block():
    """Validates that when the Kill Switch is triggered, all orders are immediately blocked."""
    engine = RiskEngine()
    gate = RiskGate(engine)
    account = create_sample_account()

    cmd = CanonicalOrderCommand(
        client_order_id="RISK-KILL-001",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=1,
        price=2.0,
        option_type=CanonicalOptionType.CALL,
        strike=350.0,
        tag_id="kill"
    )

    # 1. Normal state -> Approved
    approved, token, _ = gate.admit_order(cmd, account)
    assert approved is True

    # 2. Trigger Kill Switch -> Blocked
    engine.trigger_kill_switch("PANIC_HALT_TEST")
    approved, token, reason = gate.admit_order(cmd, account)
    assert approved is False
    assert reason == "REJECTED_BY_KILL_SWITCH"

    # 3. Reset Kill Switch -> Recovered
    engine.reset_kill_switch()
    approved, token, _ = gate.admit_order(cmd, account)
    assert approved is True
