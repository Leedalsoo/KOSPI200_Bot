"""Unit Test: Risk Gate Standalone & RiskApprovalToken Security Comprehensive Verification."""
import pytest
from datetime import datetime
import uuid

from shared.contracts.canonical import (
    CanonicalOrderCommand,
    CanonicalAccountSummary,
    CanonicalAssetType,
    CanonicalOrderSide,
    CanonicalOptionType
)
from shared.core.contracts import RiskApprovalToken
from option_program.risk_control.risk_engine import (
    RiskConfig,
    RiskEngine,
    RiskGate,
    RiskSensor
)

def create_sample_account(
    total_balance: float = 50_000_000.0,
    used_margin: float = 0.0,
    free_margin: float = 50_000_000.0,
    realized_pnl: float = 0.0
) -> CanonicalAccountSummary:
    return CanonicalAccountSummary(
        account_id="ACC-GATE-001",
        total_balance=total_balance,
        used_margin=used_margin,
        free_margin=free_margin,
        realized_pnl=realized_pnl,
        unrealized_pnl=0.0,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

def test_risk_gate_issuance_of_cryptographic_token():
    """Validates that RiskGate issues a valid RiskApprovalToken upon passing all risk gates."""
    gate = RiskGate()
    account = create_sample_account()

    cmd = CanonicalOrderCommand(
        client_order_id="ORD-GATE-001",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=2,
        price=2.50,
        option_type=CanonicalOptionType.CALL,
        strike=350.0,
        tag_id="T1-SCALP"
    )

    approved, token, reason = gate.admit_order(cmd, account)
    assert approved is True
    assert token is not None
    assert reason is None
    assert isinstance(token.order_id, uuid.UUID)
    assert token.signature.startswith("SIG-RISK-APPROVED-Track1-ORD-GATE-001")

def test_risk_gate_kill_switch_immediate_zero_delay_block():
    """Validates that RiskGate immediately blocks all orders with zero delay when Kill Switch is active."""
    engine = RiskEngine()
    gate = RiskGate(engine)
    account = create_sample_account()

    cmd = CanonicalOrderCommand(
        client_order_id="ORD-GATE-KILL",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=1,
        price=2.0,
        option_type=CanonicalOptionType.CALL,
        strike=350.0,
        tag_id="T1"
    )

    # 1. Trigger Kill Switch
    engine.trigger_kill_switch(reason="EMERGENCY_PANIC_STOP")
    approved, token, reason = gate.admit_order(cmd, account)
    assert approved is False
    assert token is None
    assert reason == "REJECTED_BY_KILL_SWITCH"

    # 2. Reset Kill Switch
    engine.reset_kill_switch()
    approved_after, token_after, reason_after = gate.admit_order(cmd, account)
    assert approved_after is True
    assert token_after is not None
    assert reason_after is None

def test_risk_gate_rejection_reasons_audit():
    """Validates all rejection reasons are clearly audited and returned."""
    config = RiskConfig(max_order_qty=10, max_daily_loss_krw=5_000_000.0)
    engine = RiskEngine(config=config)
    gate = RiskGate(engine)

    # 1. Invalid qty <= 0
    cmd_zero = CanonicalOrderCommand(
        client_order_id="ORD-R1", track_id="T1", asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY, qty=0, price=2.0, tag_id="1"
    )
    ok, _, r1 = gate.admit_order(cmd_zero, create_sample_account())
    assert ok is False and "INVALID_ORDER_QTY" in r1

    # 2. Exceeded max qty (>10)
    cmd_max_qty = CanonicalOrderCommand(
        client_order_id="ORD-R2", track_id="T1", asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY, qty=20, price=2.0, tag_id="2"
    )
    ok, _, r2 = gate.admit_order(cmd_max_qty, create_sample_account())
    assert ok is False and "EXCEEDED_MAX_ORDER_QTY" in r2

    # 3. Insufficient Free Margin
    account_low_margin = create_sample_account(free_margin=100_000.0)
    cmd_margin = CanonicalOrderCommand(
        client_order_id="ORD-R3", track_id="T1", asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY, qty=5, price=2.50, option_type=CanonicalOptionType.CALL,
        strike=350.0, tag_id="3"
    )
    ok, _, r3 = gate.admit_order(cmd_margin, account_low_margin)
    assert ok is False and "INSUFFICIENT_FREE_MARGIN" in r3
