"""Unit Test: Signal Generator Pipeline & De-duplication."""
import pytest
import time

from shared.contracts.canonical import (
    CanonicalStrategySignal,
    CanonicalOrderCommand,
    CanonicalAssetType,
    CanonicalOrderSide,
    CanonicalOptionType
)
from option_program.strategy.signal_generator import SignalGenerator

def test_signal_generator_normal_emission():
    """Validates normal strategy signal conversion into CanonicalOrderCommand."""
    gen = SignalGenerator(debounce_window_sec=1.0)
    sig = CanonicalStrategySignal(
        signal_id="SIG-001",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=2,
        price=2.50,
        option_type=CanonicalOptionType.CALL,
        strike=350.0,
        tag_id="TAG-T1-SCALP",
        reason="Scalp Entry"
    )

    cmd = gen.process_signal(sig)
    assert cmd is not None
    assert isinstance(cmd, CanonicalOrderCommand)
    assert cmd.track_id == "Track1"
    assert cmd.qty == 2
    assert cmd.price == 2.50
    assert cmd.strike == 350.0

def test_signal_generator_invalid_qty():
    """Validates that signals with zero or negative qty are rejected."""
    gen = SignalGenerator()
    sig_zero = CanonicalStrategySignal(
        signal_id="SIG-ZERO",
        track_id="Track2",
        asset_type=CanonicalAssetType.FUTURES,
        side=CanonicalOrderSide.BUY,
        qty=0,
        price=350.0,
        tag_id="TAG-ZERO"
    )
    assert gen.process_signal(sig_zero) is None

def test_signal_generator_invalid_price():
    """Validates that signals with negative or zero prices are rejected."""
    gen = SignalGenerator()
    sig_neg = CanonicalStrategySignal(
        signal_id="SIG-NEG",
        track_id="Track3",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=1,
        price=-1.5,
        option_type=CanonicalOptionType.PUT,
        strike=345.0,
        tag_id="TAG-NEG"
    )
    assert gen.process_signal(sig_neg) is None

def test_signal_generator_missing_option_fields():
    """Validates that option signals missing strike or option_type are rejected."""
    gen = SignalGenerator()
    sig_missing = CanonicalStrategySignal(
        signal_id="SIG-MISSING",
        track_id="Track4",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=1,
        price=2.0,
        option_type=None,  # Missing option_type
        strike=0.0,        # Invalid strike
        tag_id="TAG-MISSING"
    )
    assert gen.process_signal(sig_missing) is None

def test_signal_generator_deduplication():
    """Validates that rapid duplicate signals within debounce window are suppressed."""
    gen = SignalGenerator(debounce_window_sec=1.0)
    sig = CanonicalStrategySignal(
        signal_id="SIG-DUP-1",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=2,
        price=2.50,
        option_type=CanonicalOptionType.CALL,
        strike=350.0,
        tag_id="TAG-T1-DUP",
        reason="Duplicate Test"
    )

    t0 = 100.0
    # 1. First signal -> Accepted
    cmd1 = gen.process_signal(sig, current_time=t0)
    assert cmd1 is not None

    # 2. Immediate duplicate within 0.2s -> Rejected (De-duplicated)
    cmd2 = gen.process_signal(sig, current_time=t0 + 0.2)
    assert cmd2 is None

    # 3. Subsequent signal after debounce window (1.5s) -> Accepted
    cmd3 = gen.process_signal(sig, current_time=t0 + 1.5)
    assert cmd3 is not None
