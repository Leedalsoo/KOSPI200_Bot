"""Unit Test: Decision Arbiter Comprehensive Verification."""
import pytest
from datetime import datetime

from shared.contracts.canonical import (
    CanonicalStrategySignal,
    CanonicalAccountSummary,
    CanonicalAssetType,
    CanonicalOrderSide,
    CanonicalOptionType
)
from option_program.strategy.decision_arbiter import DecisionArbiter

def create_sample_account() -> CanonicalAccountSummary:
    return CanonicalAccountSummary(
        account_id="ACC-ARB-001",
        total_balance=50_000_000.0,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
        used_margin=10_000_000.0,
        free_margin=40_000_000.0,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

def test_priority_hierarchy_ordering():
    """Validates that hedge and tail defense strategies take precedence over momentum tracks."""
    arb = DecisionArbiter()
    account = create_sample_account()

    sig_momentum = CanonicalStrategySignal(
        signal_id="SIG-T2",
        track_id="Track2",
        asset_type=CanonicalAssetType.FUTURES,
        side=CanonicalOrderSide.BUY,
        qty=1,
        price=350.0,
        tag_id="T2"
    )
    sig_hedge = CanonicalStrategySignal(
        signal_id="SIG-HEDGE",
        track_id="HEDGE_DELTA",
        asset_type=CanonicalAssetType.FUTURES,
        side=CanonicalOrderSide.SELL,
        qty=1,
        price=350.0,
        tag_id="HEDGE"
    )

    res = arb.arbitrate([sig_momentum, sig_hedge], account)
    # HEDGE_DELTA is Priority 1, Track 2 is Priority 6
    # On the same instrument (FUTURES), HEDGE_DELTA SELL must win, and Track 2 BUY must be rejected
    assert len(res.approved_signals) == 1
    assert res.approved_signals[0].track_id == "HEDGE_DELTA"
    assert len(res.rejected_signals) == 1
    assert res.rejected_signals[0][0].track_id == "Track2"
    assert "CLASH_NETTING_REJECTED" in res.rejected_signals[0][1]

def test_opposite_signal_clash_resolution():
    """Validates that when Track 1 (Priority 2) and Track 5 (Priority 6) clash on Option, Track 1 wins."""
    arb = DecisionArbiter()
    account = create_sample_account()

    sig_t1_buy = CanonicalStrategySignal(
        signal_id="SIG-T1-BUY",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=2,
        price=2.50,
        option_type=CanonicalOptionType.CALL,
        strike=350.0,
        tag_id="T1-SCALP"
    )
    sig_t5_sell = CanonicalStrategySignal(
        signal_id="SIG-T5-SELL",
        track_id="Track5",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.SELL,
        qty=2,
        price=2.50,
        option_type=CanonicalOptionType.CALL,
        strike=350.0,
        tag_id="T5-GAP"
    )

    res = arb.arbitrate([sig_t5_sell, sig_t1_buy], account)
    assert len(res.approved_signals) == 1
    assert res.approved_signals[0].track_id == "Track1"
    assert res.approved_signals[0].side == CanonicalOrderSide.BUY
    assert len(res.rejected_signals) == 1
    assert res.rejected_signals[0][0].track_id == "Track5"

def test_same_side_coexistence():
    """Validates that non-clashing same-side signals on the same instrument both pass."""
    arb = DecisionArbiter()
    account = create_sample_account()

    sig_t1 = CanonicalStrategySignal(
        signal_id="SIG-T1",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=2,
        price=2.50,
        option_type=CanonicalOptionType.CALL,
        strike=350.0,
        tag_id="T1"
    )
    sig_t6 = CanonicalStrategySignal(
        signal_id="SIG-T6",
        track_id="Track6",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=1,
        price=2.50,
        option_type=CanonicalOptionType.CALL,
        strike=350.0,
        tag_id="T6"
    )

    res = arb.arbitrate([sig_t1, sig_t6], account)
    assert len(res.approved_signals) == 2
    assert len(res.rejected_signals) == 0

def test_deterministic_arbitration_order_invariant():
    """Validates that shuffling input order produces 100% deterministic arbitration."""
    arb = DecisionArbiter()
    account = create_sample_account()

    s1 = CanonicalStrategySignal(signal_id="S1", track_id="Track1", asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY, qty=2, price=2.5, option_type=CanonicalOptionType.CALL, strike=350.0, tag_id="1")
    s2 = CanonicalStrategySignal(signal_id="S2", track_id="Track2", asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.SELL, qty=2, price=2.5, option_type=CanonicalOptionType.CALL, strike=350.0, tag_id="2")
    s3 = CanonicalStrategySignal(signal_id="S3", track_id="Track3", asset_type=CanonicalAssetType.OPTION, side=CanonicalOrderSide.BUY, qty=1, price=2.0, option_type=CanonicalOptionType.PUT, strike=340.0, tag_id="3")

    res_forward = arb.arbitrate([s1, s2, s3], account)
    res_reverse = arb.arbitrate([s3, s2, s1], account)

    assert [s.signal_id for s in res_forward.approved_signals] == [s.signal_id for s in res_reverse.approved_signals]
    assert [s[0].signal_id for s in res_forward.rejected_signals] == [s[0].signal_id for s in res_reverse.rejected_signals]
