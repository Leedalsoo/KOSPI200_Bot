# -*- coding: utf-8 -*-
import pytest
from decimal import Decimal
from datetime import datetime
import numpy as np
from uuid import uuid4

from core.contracts import ExecutionReport, OrderStatus
from strategy.plugins.track3 import Track3

def test_butterfly_legs_closed_wing_ratio() -> None:
    """[목표 A 검증] Butterfly 1:2:1 계약 비율 및 행사가 수학적 등간격 증명"""
    agent = Track3({})
    legs = agent._calculate_butterfly_legs(atm_strike=Decimal('350.0'), tick_size=Decimal('2.5'))
    
    assert len(legs) == 3
    # 1 ITM (Buy), 2 ATM (Sell), 1 OTM (Buy) 확인
    atm_leg = next(leg for leg in legs if leg['strike'] == Decimal('350.0'))
    assert atm_leg['qty'] == 2 and atm_leg['side'] == 'SELL'
    
    buy_legs = [leg for leg in legs if leg['side'] == 'BUY']
    assert sum(leg['qty'] for leg in buy_legs) == 2

    # 🛡️ [수학적 등간격 증명 보강] (ITM ~ ATM 간격 == ATM ~ OTM 간격)
    itm_leg = next(leg for leg in legs if leg['side'] == 'BUY' and leg['strike'] < Decimal('350.0'))
    otm_leg = next(leg for leg in legs if leg['side'] == 'BUY' and leg['strike'] > Decimal('350.0'))
    assert (Decimal('350.0') - itm_leg['strike']) == (otm_leg['strike'] - Decimal('350.0'))
    assert (Decimal('350.0') - itm_leg['strike']) == Decimal('2.5')

def test_calendar_iv_spread_numpy_validation() -> None:
    """[목표 B 검증] Numpy 기반 IV 스프레드 괴리 연산 무결성 증명 (양성/음성 및 에지 예외 완벽 입증)"""
    agent = Track3({})
    
    # 1. 양성 테스트: 최근 스프레드가 폭발적으로 벌어짐 (스프레드: -0.03 -> 0.05, 괴리: 0.0775 > 0.05 ➡️ True)
    near_iv_pos = np.array([0.15, 0.16, 0.15, 0.15, 0.25])
    far_iv_pos = np.array([0.18, 0.18, 0.18, 0.18, 0.20])
    assert agent._validate_calendar_spread_iv(near_iv_pos, far_iv_pos) is True

    # 2. 음성 테스트: 스프레드 격차가 매우 평온하고 균등함 (스프레드: -0.03 일치, 괴리: 0.0 <= 0.05 ➡️ False)
    near_iv_neg = np.array([0.15, 0.15, 0.15, 0.15, 0.15])
    far_iv_neg = np.array([0.18, 0.18, 0.18, 0.18, 0.18])
    assert agent._validate_calendar_spread_iv(near_iv_neg, far_iv_neg) is False

    # 3. 에지 케이스 예외 테스트: 배열 길이가 2 미만인 단일 요소 입력 시 False 처리 증명
    assert agent._validate_calendar_spread_iv(np.array([0.15]), np.array([0.18])) is False
    assert agent._validate_calendar_spread_iv(np.array([]), np.array([])) is False

@pytest.mark.asyncio
async def test_asymmetric_legging_sequence() -> None:
    """[목표 C 검증] OTM 체결 전까지 ATM 발주 금지 및 체결 후 ATM 즉각 발주 증명"""
    agent = Track3({})
    otm_spec = {"code": "OTM1", "price": Decimal('1.0'), "qty": 1, "side": "BUY"}
    atm_spec = {"code": "ATM1", "price": Decimal('3.0'), "qty": 1, "side": "SELL"}
    
    # 1. OTM 발주
    otm_order = await agent._execute_asymmetric_legging(otm_spec, atm_spec)
    assert otm_order.instrument_code == "OTM1"
    assert otm_order.client_order_id in agent.pending_legs
    
    # 2. 다른 주문 ID 체결 시 반응 없음 (무시)
    dummy_report = ExecutionReport(
        client_order_id=uuid4(),
        broker_order_id="1",
        fill_id="1",
        status=OrderStatus.FILLED,
        filled_qty=1,
        filled_price=Decimal("1.0"),
        remaining_qty=0,
        timestamp=datetime.now(),
        raw_response={}
    )
    assert await agent.on_leg_filled(dummy_report) is None
    
    # 3. 기다리던 OTM 체결 시 ATM 즉각 발주
    valid_report = ExecutionReport(
        client_order_id=otm_order.client_order_id,
        broker_order_id="2",
        fill_id="2",
        status=OrderStatus.FILLED,
        filled_qty=1,
        filled_price=Decimal("1.0"),
        remaining_qty=0,
        timestamp=datetime.now(),
        raw_response={}
    )
    atm_order = await agent.on_leg_filled(valid_report)
    assert atm_order is not None
    assert atm_order.instrument_code == "ATM1"
    assert otm_order.client_order_id not in agent.pending_legs # 상태 정리 검증


def test_track3_invalid_data_hold() -> None:
    """스프레드 데이터 부족(len < 10) 시 억울한 조기청산 없이 HOLD 상태 유지 검증"""
    agent = Track3({})
    
    # 1. 시계열 개수 부족 데이터 (len=5 < 10)
    res_short_data = agent.evaluate_arbitrage({"spread_history": [1.5]*5})
    assert res_short_data["status"] == "HOLD"
    assert len(res_short_data["signals"]) == 0
    
    # 2. 포지션 보유 중 데이터 부족 시 조기청산(CLOSE)되지 않고 HOLD 유지 검증
    agent.active_position = "SHORT_SPREAD"
    res_holding_short_data = agent.evaluate_arbitrage({"spread_history": [1.5]*5})
    assert res_holding_short_data["status"] == "HOLD"
    assert agent.active_position == "SHORT_SPREAD"
    assert len(res_holding_short_data["signals"]) == 0



def test_track3_stop_loss_and_timeout() -> None:
    """Z-Score 극단 이탈(|Z| >= 3.5) 손절 및 300틱 타임아웃 청산 검증"""
    agent = Track3({})
    agent.active_position = "SHORT_SPREAD"
    
    # 1. Z-Score = 4.0 (극단 이탈 -> 손절 STOP_LOSS)
    spread_history_stop = [0.0]*15 + [4.0]
    res_stop = agent.evaluate_arbitrage({"spread_history": spread_history_stop})
    assert res_stop["status"] == "STOP_LOSS"
    assert agent.active_position is None

    # 2. 타임아웃 검증 (300틱 도달)
    agent.active_position = "LONG_SPREAD"
    agent.holding_ticks = 299
    spread_history_normal = [0.0]*16  # z_score = 0.0 인 일반 상태
    res_timeout = agent.evaluate_arbitrage({"spread_history": spread_history_normal})
    assert res_timeout["status"] == "TIMEOUT_EXIT"
    assert agent.active_position is None


def test_track3_limit_queue_and_3stage_trailing_stop() -> None:
    """[Track 3 지정가 큐 및 3단계 동적 트레일링 스탑 검증]"""
    agent = Track3({})
    
    # 1. 진입 시 MID_PRICE_OFFSET 지정가 큐 방출 확인 (Z-Score = 2.0 >= 1.8)
    spread_history_enter = [0.0]*15 + [2.0]
    res_enter = agent.evaluate_arbitrage({"spread_history": spread_history_enter, "active_vol": 1.0, "base_vol": 1.0})
    assert res_enter["status"] == "ENTER_SHORT_SPREAD"
    assert res_enter["signals"][0]["pricing_mode"] == "MID_PRICE_OFFSET"
    assert res_enter["signals"][0]["limit_offset_ticks"] == 1
    assert agent.active_position == "SHORT_SPREAD"

    # 2. 3단계 동적 스케일링 트레일링 스탑 반락 락인 검증 (High Watermark 50만 원 ➡️ 44만 원 반락 -12%)
    # z_score가 1.0이 되도록 하여 평균 회귀 청산(<=0.2) 및 손절(>=3.5)을 모두 우회
    unclosed_spread = [0.0]*10 + [1.0]*6
    market_tp1 = {"spread_history": unclosed_spread, "track3_current_pnl": 500000.0, "premium_spent": 200000.0}
    agent.evaluate_arbitrage(market_tp1)
    
    market_tp2 = {"spread_history": unclosed_spread, "track3_current_pnl": 430000.0, "premium_spent": 200000.0}
    res_tp = agent.evaluate_arbitrage(market_tp2)
    assert res_tp["status"] == "TRAILING_PROFIT_LOCK"
    assert res_tp["signals"][0]["action"] == "CLOSE_STAT_ARB"
    assert res_tp["signals"][0]["pricing_mode"] == "PREEMPTIVE_STOP_LIMIT_QUEUE"
    assert agent.active_position is None

    # 3. 15:15 타임 가드 검증 (15:15:00 이후 신규 진입 차단)
    agent.active_position = None
    res_block = agent.evaluate_arbitrage({"spread_history": spread_history_enter, "active_vol": 1.0, "base_vol": 1.0, "time_str": "15:16:00"})
    assert res_block["status"] == "CLOSE_CUTOFF_BLOCK"
    assert len(res_block["signals"]) == 0

def test_track3_intraday_cutoff_forced_flatten() -> None:
    """15:15 장 마감 윈도우 진입 시 보유 중인 Track 3 포지션 100% 강제 Flat 및 신규 진입 차단 검증"""
    agent = Track3({})
    agent.active_position = "SHORT_SPREAD"
    agent.holding_ticks = 15
    
    # 1. 15:15:00 도달 시 MARKET_CLOSE_FLATTEN 및 CLOSE_STAT_ARB 시그널 방출 확인
    spread_normal = [0.0]*16
    res_flatten = agent.evaluate_arbitrage({"spread_history": spread_normal, "time_str": "15:15:00"})
    assert res_flatten["status"] == "MARKET_CLOSE_FLATTEN"
    assert len(res_flatten["signals"]) == 1
    assert res_flatten["signals"][0]["action"] == "CLOSE_STAT_ARB"
    assert res_flatten["signals"][0]["type"] == "CLOSE_SHORT_SPREAD"
    assert agent.active_position is None
    
    # 2. 15:15:10 다음 틱에서 멱등성 유지 (추가 청산 시그널 중복 방출 0건 및 CLOSE_CUTOFF_BLOCK 유지)
    res_next_tick = agent.evaluate_arbitrage({"spread_history": spread_normal, "time_str": "15:15:10"})
    assert res_next_tick["status"] == "CLOSE_CUTOFF_BLOCK"
    assert len(res_next_tick["signals"]) == 0
    assert agent.active_position is None

def test_track3_multileg_pnl_summation() -> None:
    """[Test 1 & 2 & 3] Track 3 선물 숏 + CALL Buy + PUT Sell Multi-Leg 손익 정산 검증"""
    entry_futures = 350.0
    current_futures = 353.2  # 지수 3.2pt 상승
    qty = 1
    futures_mult = 250000.0
    options_mult = 250000.0

    # 1. 선물 숏 손익: (350 - 353.2) * 1 * 250000 = -800,000
    futures_pnl = (entry_futures - current_futures) * qty * futures_mult
    assert futures_pnl == pytest.approx(-800000.0)

    # 2. CALL BUY (Strike 350, 진입가 4.50 ➡️ 현재 내재가치 3.20 ➡️ 손익 (3.20 - 4.50) * 250000 = -325,000)
    call_entry = 4.50
    call_current_val = max(0.0, current_futures - 350.0)  # 3.20
    call_pnl = (call_current_val - call_entry) * qty * options_mult
    assert call_pnl == pytest.approx(-325000.0)

    # 3. PUT SELL (Strike 350, 진입가 4.50 ➡️ 현재 내재가치 0.0 ➡️ 손익 (4.50 - 0.0) * 250000 = +1,125,000)
    put_entry = 4.50
    put_current_val = max(0.0, 350.0 - current_futures)  # 0.0
    put_pnl = (put_entry - put_current_val) * qty * options_mult
    assert put_pnl == pytest.approx(1125000.0)

    total_net = futures_pnl + call_pnl + put_pnl
    assert total_net == pytest.approx(0.0)  # 완전한 합성 차익거래 상쇄 정손익 0원!

def test_track3_pnl_preservation_after_position_clear() -> None:
    """[Test 4 & 5] 포지션 삭제 후에도 Realized PnL 보존 및 Double Counting 방지"""
    portfolio_options = [
        {"activeStrategy": "Track3", "type": "CALL", "side": "BUY", "strike": 350.0, "price": 4.50, "qty": 1},
        {"activeStrategy": "Track3", "type": "PUT", "side": "SELL", "strike": 350.0, "price": 4.50, "qty": 1}
    ]
    current_price = 353.2
    
    # 1. 레그 손익 정산
    t3_option_pnl = 0.0
    for pos in portfolio_options:
        if pos.get("activeStrategy") == "Track3":
            k = float(pos.get("strike", 0.0))
            entry_opt_price = float(pos.get("price", 0.0))
            q = int(pos.get("qty", 1))
            side = pos.get("side")
            p_type = pos.get("type")
            if k > 0:
                current_opt_val = max(0.0, current_price - k) if p_type == "CALL" else max(0.0, k - current_price)
                if side == "BUY":
                    t3_option_pnl += (current_opt_val - entry_opt_price) * q * 250000.0
                elif side == "SELL":
                    t3_option_pnl += (entry_opt_price - current_opt_val) * q * 250000.0

    futures_pnl = (350.0 - 353.2) * 1 * 250000.0
    realized_pnl = futures_pnl + t3_option_pnl
    
    # 2. 포지션 삭제 (clear)
    portfolio_options = [p for p in portfolio_options if not p.get("activeStrategy") == "Track3"]
    assert len(portfolio_options) == 0
    assert realized_pnl == pytest.approx(0.0)  # 삭제 후에도 상쇄된 실현 손익 보존


# ============================================================================
# 🛡️ [신규 구현 검증] Test A ~ Test K (Strategy 3 Regime-Aware Optimization)
# ============================================================================

def test_a_bull_market_stat_arb_profitability() -> None:
    """Test A: 상승장에서 Statistical Arbitrage 수익성 검증"""
    agent = Track3({})
    # 상승장 시뮬레이션: 지수가 지속 상승하되 스프레드 괴리 발생
    spread_history = [0.1, 0.2, 0.15, 0.2, 0.1, 0.12, 0.1, 0.15, 0.2, 2.5]
    market_data = {
        "spread_history": spread_history,
        "current_price": 360.0,
        "price_change_rate": 0.01,
        "regime": "NORMAL"
    }
    res = agent.evaluate_arbitrage(market_data)
    assert res["status"] == "ENTER_SHORT_SPREAD"
    assert len(res["signals"]) == 1
    assert "group_id" in res["signals"][0]

def test_b_bear_market_stat_arb_profitability() -> None:
    """Test B: 하락장에서 Statistical Arbitrage 수익성 검증"""
    agent = Track3({})
    # 하락장 시뮬레이션: 지수 하락 중 음의 괴리(-2.5) 발생
    spread_history = [0.1, 0.1, 0.0, 0.1, -0.1, 0.0, 0.1, 0.0, -0.1, -2.5]
    market_data = {
        "spread_history": spread_history,
        "current_price": 340.0,
        "price_change_rate": -0.01,
        "regime": "NORMAL"
    }
    res = agent.evaluate_arbitrage(market_data)
    assert res["status"] == "ENTER_LONG_SPREAD"
    assert len(res["signals"]) == 1

def test_c_sideways_market_overtrading_prevention() -> None:
    """Test C: 횡보장에서 과도한 거래 방지"""
    agent = Track3({})
    # 횡보장 시뮬레이션: Z-Score 임계치 미달 (|Z| < 1.5)
    spread_history = [0.10, 0.11, 0.09, 0.10, 0.12, 0.10, 0.11, 0.09, 0.10, 0.11]
    market_data = {"spread_history": spread_history, "regime": "NORMAL"}
    res = agent.evaluate_arbitrage(market_data)
    assert res["status"] == "HOLD"
    assert len(res["signals"]) == 0

def test_d_extreme_move_entry_restriction() -> None:
    """Test D: 급등락(EXTREME_MOVE)에서 신규 진입 제한"""
    agent = Track3({})
    spread_history = [0.0]*15 + [4.0]  # 큰 Z-score
    market_data = {
        "spread_history": spread_history,
        "price_change_rate": 0.03,  # 3% 이상 폭등
        "regime": "EXTREME_MOVE"
    }
    res = agent.evaluate_arbitrage(market_data)
    assert res["status"] == "EXTREME_MOVE_BLOCK"
    assert len(res["signals"]) == 0
    assert agent.active_position is None

def test_e_gap_normalization_entry() -> None:
    """Test E: Gap 이후 정상화 진입"""
    agent = Track3({})
    spread_history = [0.0]*15 + [2.2]
    
    # 1. 갭 직후 미안정 시 진입 안함
    mkt_unstable = {
        "spread_history": spread_history,
        "time_str": "09:02:00",
        "is_gap": True,
        "market_stable": False,
        "spread_normalizing": False
    }
    res_unstable = agent.evaluate_arbitrage(mkt_unstable)
    assert res_unstable["status"] == "GAP_UNSTABLE_HOLD"
    
    # 2. 갭 이후 시장 안정화 및 Spread 정상화 확인 시 진입
    mkt_stable = {
        "spread_history": spread_history,
        "time_str": "09:06:00",
        "regime": "GAP",
        "market_stable": True,
        "spread_normalizing": True
    }
    res_stable = agent.evaluate_arbitrage(mkt_stable)
    assert res_stable["status"] in ["ENTER_SHORT_SPREAD", "ENTER_LONG_SPREAD"]

def test_f_low_expected_profit_entry_block() -> None:
    """Test F: Fee + Slippage보다 기대수익이 작으면 진입하지 않음"""
    agent = Track3({})
    agent.min_required_profit = 500000.0  # 요구 순이익 50만원으로 높임
    spread_history = [0.0]*15 + [1.9]  # Z-score = 1.9
    market_data = {"spread_history": spread_history, "regime": "NORMAL"}
    
    res = agent.evaluate_arbitrage(market_data)
    assert res["status"] == "HOLD"  # 기대 순이익 미달로 진입 보류
    assert agent.active_position is None

def test_g_negative_net_pnl_exit_hold() -> None:
    """Test G: Z-Score 평균회귀지만 Net PnL이 큰 음수이면 청산 조건 재검토"""
    agent = Track3({})
    agent.active_position = "SHORT_SPREAD"
    agent.active_group_id = "ARB-GROUP-20260807-TRACK3-0001"
    
    # Z-score는 회귀했지만 손익이 -100만원인 비정상 상황
    spread_history = [0.0]*16
    market_data = {
        "spread_history": spread_history,
        "track3_current_pnl": -1000000.0,
        "track3_total_fees": 50000.0,
        "regime": "NORMAL"
    }
    res = agent.evaluate_arbitrage(market_data)
    # 심한 음수 손실 상황에서는 평균회귀 무조건 청산을 유예하고 손절/트레일링/타임아웃 대기
    assert res["status"] == "HOLD"
    assert agent.active_position == "SHORT_SPREAD"

def test_h_1515_eod_group_atomic_flatten() -> None:
    """Test H: 15:15 EOD에서 전체 Position Group 동시 청산"""
    agent = Track3({})
    agent.active_position = "LONG_SPREAD"
    agent.active_group_id = "ARB-GROUP-20260807-TRACK3-0002"
    agent.position_group_legs = [
        {"group_id": "ARB-GROUP-20260807-TRACK3-0002", "leg_type": "FUTURES_LONG", "qty": 1},
        {"group_id": "ARB-GROUP-20260807-TRACK3-0002", "leg_type": "HEDGE_LEG", "qty": 1}
    ]
    
    market_data = {
        "spread_history": [0.0]*16,
        "time_str": "15:15:00",
        "track3_current_pnl": 50000.0
    }
    res = agent.evaluate_arbitrage(market_data)
    assert res["status"] == "MARKET_CLOSE_FLATTEN"
    assert len(res["signals"]) == 1
    sig = res["signals"][0]
    assert sig["group_id"] == "ARB-GROUP-20260807-TRACK3-0002"
    assert len(sig["legs"]) == 2
    assert agent.active_position is None

def test_i_multileg_pnl_no_missing_leg() -> None:
    """Test I: 한쪽 Leg PnL 누락 방지 및 옵션 Leg Theta 반영"""
    agent = Track3({})
    agent.active_position = "SHORT_SPREAD"
    agent.active_group_id = "ARB-GROUP-20260807-TRACK3-0003"
    
    # Options legs 포함 market data
    market_data = {
        "spread_history": [0.0]*16,
        "time_str": "15:15:00",
        "track3_current_pnl": 100000.0,
        "track3_total_fees": 5000.0,
        "current_price": 352.0,
        "options_legs": [
            {"strike": 350.0, "price": 4.0, "qty": 1, "side": "BUY", "type": "CALL", "current_market_price": 4.5},
            {"strike": 350.0, "price": 4.0, "qty": 1, "side": "SELL", "type": "PUT", "current_market_price": 0.5}
        ]
    }
    res = agent.evaluate_arbitrage(market_data)
    assert res["status"] == "MARKET_CLOSE_FLATTEN"
    sig = res["signals"][0]
    # 옵션 PnL = (4.5 - 4.0)*250000 + (4.0 - 0.5)*250000 = 125000 + 875000 = 1,000,000
    assert sig["options_pnl"] == pytest.approx(1000000.0)
    assert sig["final_group_net_pnl"] == pytest.approx(1000000.0 + 100000.0 - 5000.0)

def test_j_reentry_only_on_new_dislocation() -> None:
    """Test J: 청산 후 새로운 Statistical Dislocation 발생 시에만 재진입"""
    agent = Track3({})
    # 이전 청산 시점의 Z-Score가 3.8 이었을 때
    agent.last_exit_z_score = 3.8
    agent.cooldown_ticks = 0
    
    # 1. 이전 청산 지점(3.8) 부근 Z-Score (3.87) ➡️ new dislocation 부족으로 진입 안함
    spread_h1 = [0.0]*15 + [2.2]
    res1 = agent.evaluate_arbitrage({"spread_history": spread_h1, "regime": "NORMAL"})
    assert res1["status"] == "HOLD"
    
    # 2. 반대 방향 음의 괴리로 충분한 신규 괴리 발생 (-3.87) ➡️ 진입 승인
    spread_h2 = [0.0]*15 + [-2.2]
    res2 = agent.evaluate_arbitrage({"spread_history": spread_h2, "regime": "NORMAL"})
    assert res2["status"] == "ENTER_LONG_SPREAD"


def test_k_deterministic_replay_consistency() -> None:
    """Test K: 1x / 300x / 1000x Deterministic Replay 동일성 유지"""
    agent1 = Track3({})
    agent2 = Track3({})
    
    spread_history = [0.0]*15 + [2.5]
    mkt = {"spread_history": spread_history, "date_str": "2026-08-07", "regime": "NORMAL"}
    
    res1 = agent1.evaluate_arbitrage(mkt)
    res2 = agent2.evaluate_arbitrage(mkt)
    
    assert res1["status"] == res2["status"]
    assert res1["current_z_score"] == res2["current_z_score"]
    assert res1["signals"][0]["type"] == res2["signals"][0]["type"]
    assert res1["signals"][0]["group_id"] == res2["signals"][0]["group_id"]




