"""Unit Test: Hedge Engine Multi-Greek & Anti-Loop Lock Comprehensive Verification."""
import pytest
from option_program.strategy.hedge_engine import HedgeEngine, HedgeConfig
from shared.contracts.canonical import (
    CanonicalAssetType,
    CanonicalOrderSide,
    CanonicalOptionType
)

def test_delta_hedge_within_deadband():
    """Validates that delta within deadband (+-0.20) produces no hedge orders."""
    engine = HedgeEngine(HedgeConfig(delta_deadband=0.20))
    res = engine.evaluate_delta_hedge(portfolio_delta=0.15, current_futures_price=350.0)
    assert res.needs_hedge is False
    assert res.reason == "WITHIN_DELTA_DEADBAND"

def test_delta_hedge_positive_delta():
    """Validates that positive delta (+0.45) triggers a Futures SELL hedge."""
    engine = HedgeEngine(HedgeConfig(delta_deadband=0.20))
    res = engine.evaluate_delta_hedge(portfolio_delta=0.45, current_futures_price=350.0)
    assert res.needs_hedge is True
    assert res.hedge_type == "DELTA"
    assert res.command is not None
    assert res.command.asset_type == CanonicalAssetType.FUTURES
    assert res.command.side == CanonicalOrderSide.SELL
    assert res.command.qty >= 1
    assert res.command.tag_id == "RISK_HEDGE"

def test_delta_hedge_negative_delta():
    """Validates that negative delta (-0.50) triggers a Futures BUY hedge."""
    engine = HedgeEngine(HedgeConfig(delta_deadband=0.20))
    res = engine.evaluate_delta_hedge(portfolio_delta=-0.50, current_futures_price=350.0)
    assert res.needs_hedge is True
    assert res.hedge_type == "DELTA"
    assert res.command is not None
    assert res.command.asset_type == CanonicalAssetType.FUTURES
    assert res.command.side == CanonicalOrderSide.BUY

def test_tail_hedge_regime_trigger():
    """Validates that high VKOSPI or Crisis regime triggers OTM Put Tail hedge."""
    engine = HedgeEngine(HedgeConfig(tail_vkospi_threshold=30.0))
    res = engine.evaluate_tail_hedge(vkospi=32.5, current_regime="CRISIS", atm_strike=350.0)
    assert res.needs_hedge is True
    assert res.hedge_type == "TAIL"
    assert res.command is not None
    assert res.command.asset_type == CanonicalAssetType.OPTION
    assert res.command.side == CanonicalOrderSide.BUY
    assert res.command.option_type == CanonicalOptionType.PUT
    assert res.command.strike == 340.0

def test_hedge_anti_loop_lock():
    """Validates that exceeding max_hedge_count blocks further hedges (Anti-Loop Lock)."""
    engine = HedgeEngine(HedgeConfig(max_hedge_count=3, hedge_cooldown_sec=0.0))

    # Perform 3 hedges
    for i in range(3):
        res = engine.evaluate_delta_hedge(portfolio_delta=0.5, current_futures_price=350.0)
        assert res.needs_hedge is True
        engine.record_hedge_executed()

    # 4th hedge attempt -> Blocked by Anti-Loop Lock
    res_blocked = engine.evaluate_delta_hedge(portfolio_delta=0.5, current_futures_price=350.0)
    assert res_blocked.needs_hedge is False
    assert "ANTI_LOOP_LOCK" in res_blocked.reason

def test_hedge_cooldown_timer():
    """Validates that hedges within cooldown period are suppressed."""
    engine = HedgeEngine(HedgeConfig(hedge_cooldown_sec=10.0))
    t0 = 1000.0

    # 1. First hedge at t0
    res1 = engine.evaluate_delta_hedge(portfolio_delta=0.5, current_futures_price=350.0, current_time=t0)
    assert res1.needs_hedge is True
    engine.record_hedge_executed(current_time=t0)

    # 2. Immediate second hedge at t0 + 2s -> Suppressed by cooldown
    res2 = engine.evaluate_delta_hedge(portfolio_delta=0.5, current_futures_price=350.0, current_time=t0 + 2.0)
    assert res2.needs_hedge is False
    assert "COOLDOWN_ACTIVE" in res2.reason

    # 3. Third hedge at t0 + 11s -> Allowed after cooldown elapsed
    res3 = engine.evaluate_delta_hedge(portfolio_delta=0.5, current_futures_price=350.0, current_time=t0 + 11.0)
    assert res3.needs_hedge is True
