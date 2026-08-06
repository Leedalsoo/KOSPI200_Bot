# -*- coding: utf-8 -*-
import pytest
import numpy as np
from decimal import Decimal
from strategy.plugins.track4 import Track4


def test_feature_flag_seal() -> None:
    """[목표 A 검증] 설정 자산 대비 봉인(Seal) 및 활성화 경계값 대칭성 증명"""
    agent = Track4({}, equity_threshold=Decimal("10000000000")) # 100억
    
    # 1. 미달 자산 (50억 ➡️ False)
    assert agent._check_feature_flag(Decimal("5000000000")) is False
    
    # 2. 정확히 임계 자산 (100억 ➡️ True)
    assert agent._check_feature_flag(Decimal("10000000000")) is True
    
    # 3. 초과 자산 (150억 ➡️ True)
    assert agent._check_feature_flag(Decimal("15000000000")) is True

def test_dynamic_deadband_range() -> None:
    """[목표 B 검증] 0.2 ~ 0.6 밴드 수축/확장 정합성 및 극단적/극초기 경계값 검증"""
    agent = Track4({}, Decimal("0"))
    
    # 1. 일반적 변동성 범위 검증
    high_vals = np.array([100.0, 105.0])
    low_vals = np.array([95.0, 98.0])
    close_vals = np.array([102.0, 99.0])
    band = agent._calculate_atr_deadband(high_vals, low_vals, close_vals)
    assert Decimal("0.2") <= band <= Decimal("0.6")

    # 2. 극소 변동성 (변동성 제로 ➡️ 하한 0.2 수렴)
    high_zero = np.array([100.0, 100.0])
    low_zero = np.array([100.0, 100.0])
    close_zero = np.array([100.0, 100.0])
    band_zero = agent._calculate_atr_deadband(high_zero, low_zero, close_zero)
    assert band_zero == Decimal("0.2")

    # 3. 극대 변동성 (변동성 폭발 ➡️ 상한 0.6 클램핑)
    high_max = np.array([100.0, 1000.0])
    low_max = np.array([100.0, 10.0])
    close_max = np.array([100.0, 100.0])
    band_max = agent._calculate_atr_deadband(high_max, low_max, close_max)
    assert band_max == Decimal("0.6")

    # 4. 극초기 상태 (데이터 1개 유입 ➡️ 크래시 없이 정상 계산)
    high_init = np.array([100.0])
    low_init = np.array([90.0])
    close_init = np.array([95.0])
    band_init = agent._calculate_atr_deadband(high_init, low_init, close_init)
    assert Decimal("0.2") <= band_init <= Decimal("0.6")

def test_gamma_profit_offset() -> None:
    """[목표 C 검증] 세타 비용 대비 감마 수익 상쇄 및 동률 임계점 분기 증명"""
    agent = Track4({}, Decimal("0"))
    
    # 1. 수익 > 비용 (True)
    assert agent._verify_theta_decay_offset(Decimal("1000"), Decimal("500")) is True
    
    # 2. 수익 < 비용 (False)
    assert agent._verify_theta_decay_offset(Decimal("100"), Decimal("500")) is False

    # 3. 수익 == 비용 (동률 경계값 ➡️ False)
    assert agent._verify_theta_decay_offset(Decimal("1000"), Decimal("1000")) is False


@pytest.mark.asyncio
async def test_track4_delta_hedging_independent_of_theta() -> None:

    """[핵심 검증] 세타 비용 손실 조건에도 델타 헷지가 차단되지 않고 독립 작동함 증명"""
    from datetime import datetime
    from core.contracts import MarketTick
    
    # 세타 수익 < 세타 비용 (세타 가드 조건 실패 상태)
    context = {
        "current_equity": Decimal("100"),
        "accumulated_profit": Decimal("100"),
        "decay_cost": Decimal("500")
    }
    agent = Track4(context, equity_threshold=Decimal("0"))
    
    tick = MarketTick(
        instrument_code="KOSPI200_FUT",
        timestamp=datetime.now(),
        last_price=Decimal("350.00"),
        volume=10,
        bid_prices=[Decimal("349.95")],
        ask_prices=[Decimal("350.05")],
        bid_qtys=[5],
        ask_qtys=[5]
    )
    
    # 델타 = 1.5 > 데드밴드(0.2) ➡️ 델타 헷지 주문이 세타 가드 실패에도 불구하고 생성되어야 함 (1.5 반올림 ➡️ 2계약 매도)
    orders = await agent.on_tick(tick, current_gamma=Decimal("0.05"), current_delta=Decimal("1.5"))
    assert len(orders) == 1
    assert orders[0].side == "SELL"
    assert orders[0].qty == 2
    assert orders[0].instrument_code == "FUT_HEDGE"



@pytest.mark.asyncio
async def test_track4_deactivation_unwind() -> None:
    """[비활성화 검증] 전략 비활성화 시 잔여 선물 헷지 언와인드(청산) 발주 증명"""
    from datetime import datetime
    from core.contracts import MarketTick
    
    context = {"current_equity": Decimal("100")}
    agent = Track4(context, equity_threshold=Decimal("0"))
    agent.active_hedge_qty = 2  # 기존 선물 헷지 매수 2계약 보유 중
    
    # 자산 미달로 비활성화 전환 (equity_threshold 500 > equity 100)
    agent.equity_threshold = Decimal("500")
    
    tick = MarketTick(
        instrument_code="KOSPI200_FUT",
        timestamp=datetime.now(),
        last_price=Decimal("350.00"),
        volume=10,
        bid_prices=[Decimal("349.95")],
        ask_prices=[Decimal("350.05")],
        bid_qtys=[5],
        ask_qtys=[5]
    )
    
    orders = await agent.on_tick(tick, current_gamma=Decimal("0"), current_delta=Decimal("0"))
    assert len(orders) == 1
    assert orders[0].side == "SELL"
    assert orders[0].qty == 2
    assert agent.active_hedge_qty == 0


def test_track4_limit_queue_and_3stage_trailing_stop() -> None:
    """[Track 4 신규 기능 검증] 지정가 큐 델타 리밸런싱 및 3단계 동적 스케일링 스탑 검증"""
    agent = Track4({})
    
    # 1. 델타 0.5 > 데드밴드(0.3) ➡️ MID_PRICE_OFFSET 지정가 큐 리밸런싱
    market_data = {"current_delta": 0.5, "deadband": 0.3}
    res_reb = agent.evaluate_scalping_rebalance(market_data, days_to_expiry=10.0)
    assert res_reb["status"] == "REBALANCE"
    assert res_reb["signals"][0]["action"] == "GAMMA_REBALANCE"
    assert res_reb["signals"][0]["pricing_mode"] == "MID_PRICE_OFFSET"

    # 2. 3단계 동적 스케일링 트레일링 스탑 검증 (High Watermark 50만 원 ➡️ 44만 원 반락 -12%)
    market_tp1 = {"track4_current_pnl": 500000.0, "premium_spent": 200000.0}
    agent.evaluate_scalping_take_profit(market_tp1)
    
    market_tp2 = {"track4_current_pnl": 430000.0, "premium_spent": 200000.0}  # 50만 * 0.88 = 44만 원 이하
    res_tp = agent.evaluate_scalping_take_profit(market_tp2)
    assert res_tp["status"] == "PROFIT_TAKEN_TRAILING_STOP"
    assert res_tp["signals"][0]["action"] == "CLOSE_GAMMA_SCALP_LIMIT"
    assert res_tp["signals"][0]["pricing_mode"] == "PREEMPTIVE_STOP_LIMIT_QUEUE"


def test_track4_hybrid_basecamp_entry() -> None:
    """[Track 4 하이브리드 베이스캠프 검증] 저변동성 5pt 폭 OTM 1단 vs 고변동성 ATM 정중앙 베이스캠프 스위칭 검증"""
    agent = Track4({})
    
    # 1. 저변동성 (active_vol = 0.8 <= 0.85) ➡️ 5.0pt 폭 OTM 1단 베이스캠프 (Call: 352.5, Put: 347.5)
    res_wide = agent.evaluate_scalping_basecamp_entry(
        current_price=350.0,
        active_vol=0.8,
        base_vol=1.0,
        date_str="2026-08-06"
    )
    assert res_wide["status"] == "WIDE_BASECAMP_TRIGGERED"
    assert res_wide["signals"][0]["action"] == "BUILD_HYBRID_BASECAMP"
    assert res_wide["signals"][0]["call_strike"] == 352.5
    assert res_wide["signals"][0]["put_strike"] == 347.5
    assert agent.basecamp_active is True

    # 2. 영업일 변경 후 고변동성 (active_vol = 1.4 >= 1.30) ➡️ ATM 정중앙 베이스캠프 (Call: 350.0, Put: 350.0)
    res_atm = agent.evaluate_scalping_basecamp_entry(
        current_price=350.0,
        active_vol=1.4,
        base_vol=1.0,
        date_str="2026-08-07"
    )
    assert res_atm["status"] == "ATM_BASECAMP_TRIGGERED"
    assert res_atm["signals"][0]["action"] == "BUILD_HYBRID_BASECAMP"
    assert res_atm["signals"][0]["call_strike"] == 350.0
    assert res_atm["signals"][0]["put_strike"] == 350.0
    assert agent.basecamp_active is True

    # 3. 15:15 타임 가드 검증 (15:15:00 이후 진입 차단)
    agent.basecamp_active = False
    res_block = agent.evaluate_scalping_basecamp_entry(
        current_price=350.0,
        active_vol=0.8,
        base_vol=1.0,
        date_str="2026-08-08",
        time_str="15:16:00"
    )
    assert res_block["status"] == "CLOSE_CUTOFF_BLOCK"
    assert len(res_block["signals"]) == 0






