from decimal import Decimal
import logging
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from uuid import uuid4
from option_program.strategy.common import TradingDateResetHelper, ExecutionCostCalculator, WallClockTimer
from option_program.strategy.strategy_contract import StrategyContract

logger = logging.getLogger(__name__)

class Track3(StrategyContract):
    """
    [Track3] Regime-Aware 통계적 차익거래 모듈 (Statistical Arbitrage / Pairs Trading)
    - 자본 배분: 5% (통계적 무위험 현금 알파 수취 모듈)
    - 최우선 원칙:
      1. 시장 방향을 예측하지 않으며, 상대가격의 통계적 괴리가 정상화되는 과정에서 발생하는 차익을 추구함.
      2. 상승장, 하락장, 횡보장, 급등락, 갭, 고변동성 등 모든 시장 상황에서 작동함.
      3. 시장 Regime(NORMAL, HIGH_VOLATILITY, EXTREME_MOVE, GAP)에 따라 진입 임계치, 기대수익, 슬리피지, 
         포지션 크기, 청산 기준, 거래 빈도를 동적으로 조정함.
    """
    def __init__(self, config: Dict[str, Any]):
        self.params = config.get("strategies", {}).get("strategy_3", {}).get("params", {})
        self.max_group_limit = self.params.get("max_group_limit", 2)
        self.z_entry_threshold = self.params.get("z_score_threshold", 2.0)
        self.z_exit_threshold = self.params.get("z_exit_threshold", 0.2)
        self.z_stop_loss_threshold = self.params.get("z_stop_loss_threshold", 3.5)  # 극단 이탈 손절
        self.max_holding_ticks = self.params.get("max_holding_ticks", 300)  # 타임아웃 청산
        
        # 비용 및 최소 기대수익 기준 (원 단위 및 틱/스프레드 단위)
        self.min_required_profit = float(self.params.get("min_required_profit", 15000.0))  # 기본 1.5만원 이상 순이익 필요
        self.base_round_trip_cost = float(self.params.get("base_round_trip_cost", 10000.0))  # 기본 왕복 수수료+슬리피지 1만원
        
        # 내부 상태 관리
        self.active_position: Optional[str] = None  # "SHORT_SPREAD" 또는 "LONG_SPREAD" 또는 None
        self.active_group_id: Optional[str] = None   # Position Group ID (예: ARB-GROUP-20260807-TRACK3-0001)
        self.group_sequence: int = 0
        self.cooldown_ticks = 0
        self.holding_ticks = 0
        self.last_exit_z_score: Optional[float] = None
        self.date_reset_helper = TradingDateResetHelper()
        self.pending_legs: Dict[Any, Dict[str, Any]] = {}
        self._arb_high_pnl: float = 0.0
        
        # Position Group 구성 레그 추적
        self.position_group_legs: List[Dict[str, Any]] = []
        self.group_integrity: bool = True
        
        logger.info("Statistical Arbitrage Strategy (Track3) Initialized with Regime-Aware Optimization.")

    def _calculate_butterfly_legs(self, atm_strike: Decimal, tick_size: Decimal) -> List[Dict[str, Any]]:
        return [
            {'strike': atm_strike - tick_size, 'qty': 1, 'side': 'BUY'},
            {'strike': atm_strike, 'qty': 2, 'side': 'SELL'},
            {'strike': atm_strike + tick_size, 'qty': 1, 'side': 'BUY'}
        ]

    def _validate_calendar_spread_iv(self, near_iv: np.ndarray, far_iv: np.ndarray) -> bool:
        if len(near_iv) < 2 or len(far_iv) < 2 or len(near_iv) != len(far_iv):
            return False
        spreads = near_iv - far_iv
        mean_spread = float(np.mean(spreads[:-1]))
        current_spread = float(spreads[-1])
        divergence = abs(current_spread - mean_spread)
        return divergence > 0.05

    async def _execute_asymmetric_legging(self, otm_spec: Dict[str, Any], atm_spec: Dict[str, Any]) -> Any:
        from decimal import Decimal
        import time
        from core.contracts import OrderRequest
        now_ns = time.time_ns()
        client_id = uuid4()
        otm_order = OrderRequest(
            decision_id=uuid4(),
            client_order_id=client_id,
            instrument_code=otm_spec.get("code", "OTM"),
            price=otm_spec.get("price", Decimal("1.0")),
            qty=otm_spec.get("qty", 1),
            side=otm_spec.get("side", "BUY"),
            timestamp_ns=now_ns
        )
        self.pending_legs[client_id] = atm_spec
        return otm_order

    async def on_leg_filled(self, report: Any) -> Any:
        if report.client_order_id not in self.pending_legs:
            return None
        
        atm_spec = self.pending_legs.pop(report.client_order_id)
        from decimal import Decimal
        import time
        from core.contracts import OrderRequest
        now_ns = time.time_ns()
        atm_order = OrderRequest(
            decision_id=uuid4(),
            client_order_id=uuid4(),
            instrument_code=atm_spec.get("code", "ATM"),
            price=atm_spec.get("price", Decimal("1.0")),
            qty=atm_spec.get("qty", 1),
            side=atm_spec.get("side", "SELL"),
            timestamp_ns=now_ns
        )
        return atm_order

    def calculate_z_score(self, spread_series: List[float]) -> Tuple[float, bool]:
        """
        주어진 스프레드 시세 리스트를 바탕으로 현재 Z-Score 산출
        Returns:
            (z_score, is_valid)
        """
        if not spread_series or len(spread_series) < 10:
            return 0.0, False
        
        arr = np.array(spread_series)
        mean = np.mean(arr)
        std = np.std(arr)
        
        if std == 0:
            return 0.0, True
        
        current_spread = spread_series[-1]
        z_score = (current_spread - mean) / std
        return float(z_score), True

    def detect_market_regime(self, market_data: Dict[str, Any]) -> str:
        """
        Market Data를 바탕으로 Strategy 3 전용 시장 국면(Regime) 판별:
        - REGIME A: NORMAL (변동성 정상, 호가 정상, 스프레드 정상)
        - REGIME B: HIGH_VOLATILITY (단기 실현변동성/ATR/스프레드 급증)
        - REGIME C: EXTREME_MOVE (급등/급락 및 비정상적 가격 폭승/폭락)
        - REGIME D: GAP (장 시작 직후 시초가 갭 발생 및 미안정 상태)
        """
        explicit_regime = market_data.get("regime") or market_data.get("current_regime")
        if explicit_regime in ["HIGH_VOL", "HIGH_VOLATILITY"]:
            return "HIGH_VOLATILITY"
        elif explicit_regime in ["EXTREME_MOVE", "CIRCUIT_BREAKER", "CRASH"]:
            return "EXTREME_MOVE"
        elif explicit_regime in ["GAP", "GAP_OPEN"]:
            return "GAP"

        active_vol = float(market_data.get("active_vol", 1.0))
        base_vol = float(market_data.get("base_vol", 1.0))
        vol_ratio = active_vol / max(0.1, base_vol)

        time_str = market_data.get("time_str", "09:00:00")
        is_gap_flag = market_data.get("is_gap", False) or (time_str < "09:05:00" and abs(float(market_data.get("gap_pct", 0.0))) >= 0.008)

        if is_gap_flag:
            return "GAP"

        price_change_rate = abs(float(market_data.get("price_change_rate", 0.0)))
        if price_change_rate >= 0.02 or vol_ratio >= 2.5:
            return "EXTREME_MOVE"
        elif vol_ratio >= 1.4 or float(market_data.get("bid_ask_spread", 0.0)) > 0.3:
            return "HIGH_VOLATILITY"

        return "NORMAL"

    def estimate_round_trip_cost(self, regime: str, qty: int, market_data: Dict[str, Any]) -> float:
        """
        왕복 거래비용 사전 계산 (Entry Fee + Exit Fee + Entry Slippage + Exit Slippage + Bid/Ask Spread + Partial Fill)
        """
        bid_ask_spread = float(market_data.get("bid_ask_spread", 0.05)) * 250000.0
        fee_per_leg = 3000.0  # Leg당 왕복 수수료 추정값
        slippage_ticks = 1.0 if regime == "NORMAL" else (2.0 if regime == "HIGH_VOLATILITY" else 3.0)
        slippage_cost = slippage_ticks * 0.05 * 250000.0 * qty
        
        total_estimated_cost = (fee_per_leg * 2 * qty) + slippage_cost + (bid_ask_spread * qty) + self.base_round_trip_cost
        return total_estimated_cost

    def calculate_expected_gross_profit(self, z_score: float, spread_history: List[float], qty: int) -> float:
        """
        Z-Score 괴리분 기반 expected gross arbitrage profit (KRW) 계산
        """
        if not spread_history or len(spread_history) < 10:
            return 0.0
        arr = np.array(spread_history)
        std = np.std(arr)
        # mean reversion시 기대되는 포인트 이익 = abs(z_score) * std * 0.8
        expected_points = abs(z_score) * std * 0.8
        expected_gross_krw = expected_points * 250000.0 * qty
        return float(expected_gross_krw)

    def calculate_options_carry_and_theta(self, market_data: Dict[str, Any]) -> float:
        """
        옵션 Leg가 포함되어 있을 경우 Time Value, Intrinsic Value, Theta, IV 변화 반영
        """
        options_legs = market_data.get("options_legs", [])
        total_options_pnl = 0.0
        current_index = float(market_data.get("current_price", market_data.get("futures_price", 350.0)))
        
        for leg in options_legs:
            k = float(leg.get("strike", 0.0))
            entry_price = float(leg.get("price", 0.0))
            qty = int(leg.get("qty", 1))
            side = leg.get("side", "BUY")
            p_type = leg.get("type", "CALL")
            
            if k > 0:
                intrinsic_val = max(0.0, current_index - k) if p_type == "CALL" else max(0.0, k - current_index)
                # 현재 시장가격 (없으면 내재가치 + 잔존시간가치)
                market_price = float(leg.get("current_market_price", intrinsic_val))
                
                if side == "BUY":
                    total_options_pnl += (market_price - entry_price) * qty * 250000.0
                elif side == "SELL":
                    total_options_pnl += (entry_price - market_price) * qty * 250000.0
        return total_options_pnl

    def evaluate_arbitrage(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        [메인 통계 차익 평가 루틴]
        - 현선물 가격 데이터 및 최근 스프레드 시세를 받아 Z-Score 및 Regime 분석 후 시그널 발행.
        """
        current_date = market_data.get("date_str", "UNKNOWN")
        if self.date_reset_helper.check_and_update(current_date):
            self.cooldown_ticks = 0
            self.holding_ticks = 0
            self.active_position = None
            self.active_group_id = None
            self.last_exit_z_score = None
            self.position_group_legs = []
            self.group_integrity = True

        spread_history = market_data.get("spread_history", [])
        raw_fees = market_data.get("track3_total_fees") if market_data.get("track3_total_fees") is not None else market_data.get("total_fees", 0.0)
        raw_pnl = market_data.get("track3_current_pnl") if market_data.get("track3_current_pnl") is not None else market_data.get("current_pnl", 0.0)
        total_fees: float = float(raw_fees or 0.0)
        current_pnl: float = float(raw_pnl or 0.0)
        
        # Options Carry / Theta 반영 PnL
        options_pnl = self.calculate_options_carry_and_theta(market_data)
        effective_current_pnl = current_pnl + options_pnl

        z_score, is_valid = self.calculate_z_score(spread_history)
        regime = self.detect_market_regime(market_data)

        # Regime별 동적 진입 임계치 및 Sizing 산정
        active_vol = float(market_data.get("active_vol", 1.0))
        base_vol = float(market_data.get("base_vol", 1.0))
        vol_ratio = active_vol / max(0.1, base_vol)

        if regime == "HIGH_VOLATILITY":
            effective_z_entry = max(2.2, self.z_entry_threshold * vol_ratio * 1.2)
            min_net_profit_req = self.min_required_profit * 1.5
            pos_qty = 1
        elif regime == "EXTREME_MOVE":
            effective_z_entry = 999.0  # 차단
            min_net_profit_req = self.min_required_profit * 3.0
            pos_qty = 0
        elif regime == "GAP":
            effective_z_entry = max(2.0, self.z_entry_threshold * 1.1)
            min_net_profit_req = self.min_required_profit * 1.3
            pos_qty = 1
        else:  # NORMAL
            effective_z_entry = max(1.5, self.z_entry_threshold * vol_ratio)
            min_net_profit_req = self.min_required_profit
            # 매우 높은 Statistical Dislocation시 확대 허용
            pos_qty = 2 if abs(z_score) >= 2.5 and market_data.get("allow_size_up", False) else 1

        signals = []
        status = "HOLD"
        
        if self.cooldown_ticks > 0:
            self.cooldown_ticks -= 1

        # 데이터 부족/std==0인 경우 조기 청산 방지 -> HOLD
        if not is_valid:
            return {
                "strategy": "Strategy_3_StatArb",
                "active": self.active_position is not None,
                "current_z_score": 0.0,
                "status": "HOLD",
                "regime": regime,
                "signals": []
            }

        time_str = market_data.get("time_str", "09:00:00")

        # 1. 포지션이 없는 경우: 진입 조건 탐색 (Candidate A: 15:00:00 이후 오버나잇 신규 진입 차단)
        if self.active_position is None:
            if time_str >= "15:00:00":
                return {
                    "strategy": "Strategy_3_StatArb",
                    "active": False,
                    "current_z_score": z_score,
                    "status": "CLOSE_CUTOFF_BLOCK",
                    "regime": regime,
                    "signals": []
                }

            # EXTREME_MOVE 시 신규 진입 차단
            if regime == "EXTREME_MOVE":
                return {
                    "strategy": "Strategy_3_StatArb",
                    "active": False,
                    "current_z_score": z_score,
                    "status": "EXTREME_MOVE_BLOCK",
                    "regime": regime,
                    "signals": []
                }

            # GAP 국면 안정화 확인: Bid/Ask Spread 및 예상 순이익 만족 여부
            if regime == "GAP":
                market_stable = market_data.get("market_stable", True)
                spread_normalizing = market_data.get("spread_normalizing", True)
                if not (market_stable and spread_normalizing):
                    return {
                        "strategy": "Strategy_3_StatArb",
                        "active": False,
                        "current_z_score": z_score,
                        "status": "GAP_UNSTABLE_HOLD",
                        "regime": regime,
                        "signals": []
                    }

            if self.cooldown_ticks == 0:
                # 🛡️ [재진입 엄격화 필터] 이전 청산 Z-Score 대비 새로운 Statistical Dislocation 발생 여부 검증
                is_new_dislocation = True
                if self.last_exit_z_score is not None:
                    if abs(z_score - self.last_exit_z_score) < 0.8:
                        is_new_dislocation = False

                if is_new_dislocation:
                    # 🛡️ [비용 및 예상 순이익 사전 평가] Expected Net Arbitrage Profit > Minimum Required Profit
                    expected_cost = self.estimate_round_trip_cost(regime, pos_qty, market_data)
                    expected_gross = self.calculate_expected_gross_profit(z_score, spread_history, pos_qty)
                    expected_net_profit = expected_gross - expected_cost

                    if expected_net_profit >= min_net_profit_req:
                        if z_score >= effective_z_entry:
                            self.group_sequence += 1
                            self.active_group_id = f"ARB-GROUP-{current_date.replace('-', '')}-TRACK3-{self.group_sequence:04d}"
                            self.active_position = "SHORT_SPREAD"
                            self.holding_ticks = 0
                            self._arb_high_pnl = 0.0
                            self.group_integrity = True
                            self.position_group_legs = [
                                {"group_id": self.active_group_id, "leg_type": "FUTURES_SHORT", "qty": pos_qty},
                                {"group_id": self.active_group_id, "leg_type": "HEDGE_LEG", "qty": pos_qty}
                            ]
                            status = "ENTER_SHORT_SPREAD"
                            signals.append({
                                "action": "EXECUTE_STAT_ARB",
                                "type": "SHORT_SPREAD",
                                "group_id": self.active_group_id,
                                "z_score": z_score,
                                "pricing_mode": "MID_PRICE_OFFSET",
                                "limit_offset_ticks": 1,
                                "fallback_market_timeout_sec": 2.0,
                                "qty": pos_qty,
                                "expected_net_pnl": expected_net_profit,
                                "regime": regime,
                                "reason": f"Z-Score ({z_score:.2f}) >= threshold ({effective_z_entry:.2f}) & Expected Net PnL (KRW {expected_net_profit:,.0f}) >= Min ({min_net_profit_req:,.0f}). Group ID: {self.active_group_id}"
                            })
                        elif z_score <= -effective_z_entry:
                            self.group_sequence += 1
                            self.active_group_id = f"ARB-GROUP-{current_date.replace('-', '')}-TRACK3-{self.group_sequence:04d}"
                            self.active_position = "LONG_SPREAD"
                            self.holding_ticks = 0
                            self._arb_high_pnl = 0.0
                            self.group_integrity = True
                            self.position_group_legs = [
                                {"group_id": self.active_group_id, "leg_type": "FUTURES_LONG", "qty": pos_qty},
                                {"group_id": self.active_group_id, "leg_type": "HEDGE_LEG", "qty": pos_qty}
                            ]
                            status = "ENTER_LONG_SPREAD"
                            signals.append({
                                "action": "EXECUTE_STAT_ARB",
                                "type": "LONG_SPREAD",
                                "group_id": self.active_group_id,
                                "z_score": z_score,
                                "pricing_mode": "MID_PRICE_OFFSET",
                                "limit_offset_ticks": 1,
                                "fallback_market_timeout_sec": 2.0,
                                "qty": pos_qty,
                                "expected_net_pnl": expected_net_profit,
                                "regime": regime,
                                "reason": f"Z-Score ({z_score:.2f}) <= threshold (-{effective_z_entry:.2f}) & Expected Net PnL (KRW {expected_net_profit:,.0f}) >= Min ({min_net_profit_req:,.0f}). Group ID: {self.active_group_id}"
                            })

        # 2. 포지션을 보유 중인 경우: 15:15 EOD 처리, 손절/타임아웃, 3중 청산 판단 (Convergence + Profitability + Integrity)
        else:
            self.holding_ticks += 1
            
            # (0) 🛡️ [15:15 EOD 원자적 완전 청산] 전체 Position Group 동시 완전 청산 및 통합 Ledger 기록
            if time_str >= "15:15:00":
                action_type = "CLOSE_SHORT_SPREAD" if self.active_position == "SHORT_SPREAD" else "CLOSE_LONG_SPREAD"
                
                # 레그 누락 검증 (Structural Integrity)
                group_pnl = effective_current_pnl - total_fees
                
                signals.append({
                    "action": "CLOSE_STAT_ARB",
                    "type": action_type,
                    "group_id": self.active_group_id,
                    "legs": self.position_group_legs,
                    "z_score": z_score,
                    "qty": 1,
                    "final_group_net_pnl": group_pnl,
                    "total_fees": total_fees,
                    "options_pnl": options_pnl,
                    "reason": f"⏰ [15:15 EOD] 전체 Position Group({self.active_group_id}) 100% 동시 완전 청산 및 통합 회계 기록 (Net PnL: KRW {group_pnl:,.0f})"
                })
                self.last_exit_z_score = z_score
                self.active_position = None
                self.active_group_id = None
                self.cooldown_ticks = 20
                self.holding_ticks = 0
                return {
                    "strategy": "Strategy_3_StatArb",
                    "active": False,
                    "current_z_score": z_score,
                    "status": "MARKET_CLOSE_FLATTEN",
                    "regime": regime,
                    "signals": signals
                }

            # (A) 3단계 동적 트레일링 스탑 락인
            prev_high = getattr(self, "_arb_high_pnl", 0.0)
            current_high = max(prev_high, effective_current_pnl)
            self._arb_high_pnl = current_high
            spent = float(market_data.get("premium_spent", 200000.0))

            if current_high > 30000.0:
                pnl_ratio = current_high / max(1.0, spent)
                if pnl_ratio >= 2.0:
                    trailing_ratio = 0.90
                    step_name = "3단계(+100% 이상 잭팟 -10% 타이트)"
                elif pnl_ratio >= 1.3:
                    trailing_ratio = 0.88
                    step_name = "2단계(+30%~+100% -12% 조임)"
                else:
                    trailing_ratio = 0.85
                    step_name = "1단계(+30% 미만 -15% 유지)"

                stop_trigger_pnl = current_high * trailing_ratio

                if effective_current_pnl <= stop_trigger_pnl:
                    action_type = "CLOSE_SHORT_SPREAD" if self.active_position == "SHORT_SPREAD" else "CLOSE_LONG_SPREAD"
                    signals.append({
                        "action": "CLOSE_STAT_ARB",
                        "type": action_type,
                        "group_id": self.active_group_id,
                        "pricing_mode": "PREEMPTIVE_STOP_LIMIT_QUEUE",
                        "limit_offset_ticks": 2,
                        "fallback_market_timeout_sec": 2.0,
                        "z_score": z_score,
                        "qty": 1,
                        "reason": f"🚀 [STAT ARB LOCK] High Watermark (KRW {current_high:,.0f}) 대비 {step_name} 반락. 선제 지정가 익절! Group ID: {self.active_group_id}"
                    })
                    self.last_exit_z_score = z_score
                    self.active_position = None
                    self.active_group_id = None
                    self.cooldown_ticks = 20
                    self.holding_ticks = 0
                    return {"strategy": "Strategy_3_StatArb", "active": False, "status": "TRAILING_PROFIT_LOCK", "regime": regime, "signals": signals}

            # (B) Z-Score 극단 이탈 손절
            is_stop_loss = False
            if self.active_position == "SHORT_SPREAD" and z_score >= self.z_stop_loss_threshold:
                is_stop_loss = True
            elif self.active_position == "LONG_SPREAD" and z_score <= -self.z_stop_loss_threshold:
                is_stop_loss = True

            # (C) 최대 보유시간 타임아웃
            is_timeout = (self.holding_ticks >= self.max_holding_ticks)

            if is_stop_loss:
                reason_str = f"Z-Score extreme breach ({z_score:.2f} >= {self.z_stop_loss_threshold}). Stop loss triggered. Group ID: {self.active_group_id}"
                action_type = "CLOSE_SHORT_SPREAD" if self.active_position == "SHORT_SPREAD" else "CLOSE_LONG_SPREAD"
                signals.append({
                    "action": "CLOSE_STAT_ARB",
                    "type": action_type,
                    "group_id": self.active_group_id,
                    "z_score": z_score,
                    "qty": 1,
                    "reason": reason_str
                })
                self.last_exit_z_score = z_score
                self.active_position = None
                self.active_group_id = None
                self.cooldown_ticks = 40  # 손절 후 40틱 쿨다운
                self.holding_ticks = 0
                status = "STOP_LOSS"

            elif is_timeout:
                reason_str = f"Holding time limit reached ({self.holding_ticks} ticks >= {self.max_holding_ticks}). Timeout exit. Group ID: {self.active_group_id}"
                action_type = "CLOSE_SHORT_SPREAD" if self.active_position == "SHORT_SPREAD" else "CLOSE_LONG_SPREAD"
                signals.append({
                    "action": "CLOSE_STAT_ARB",
                    "type": action_type,
                    "group_id": self.active_group_id,
                    "z_score": z_score,
                    "qty": 1,
                    "reason": reason_str
                })
                self.last_exit_z_score = z_score
                self.active_position = None
                self.active_group_id = None
                self.cooldown_ticks = 20
                self.holding_ticks = 0
                status = "TIMEOUT_EXIT"

            else:
                # 🛡️ [3중 청산 판단] Statistical Convergence + Economic Profitability + Structural Integrity
                is_converged = (self.active_position == "SHORT_SPREAD" and z_score <= self.z_exit_threshold) or \
                               (self.active_position == "LONG_SPREAD" and z_score >= -self.z_exit_threshold)

                # Economic Profitability: 비용 및 수수료를 감안한 예상 순손익이 양수(또는 최소 이익선 만족)인지 검증
                # 단, 수수료/비용 차감 후 Net PnL이 음수인 경우 평균회귀만으로 무조건 청산하지 않고 보류
                cost_estimate = self.estimate_round_trip_cost(regime, 1, market_data)
                expected_exit_net_pnl = effective_current_pnl - total_fees - cost_estimate
                is_economically_profitable = (expected_exit_net_pnl >= -5000.0)  # 음수 손실 확정 방어 기준 (-5000원 이하 손실청산 방어)

                # HIGH_VOLATILITY에서는 더 빠른 Profit Take 허용
                if regime == "HIGH_VOLATILITY" and effective_current_pnl > 10000.0:
                    is_economically_profitable = True

                # GAP 이후 빠른 정상화 시 조기 청산 허용
                if regime == "GAP" and is_converged and effective_current_pnl > 5000.0:
                    is_economically_profitable = True

                if is_converged and is_economically_profitable and self.group_integrity:
                    action_type = "CLOSE_SHORT_SPREAD" if self.active_position == "SHORT_SPREAD" else "CLOSE_LONG_SPREAD"
                    reason_str = f"Z-Score returned to mean ({z_score:.2f}) with Economic Profitability (Net PnL: KRW {expected_exit_net_pnl:,.0f}). Group ID: {self.active_group_id}"
                    signals.append({
                        "action": "CLOSE_STAT_ARB",
                        "type": action_type,
                        "group_id": self.active_group_id,
                        "pricing_mode": "MID_PRICE_OFFSET",
                        "limit_offset_ticks": 1,
                        "z_score": z_score,
                        "qty": 1,
                        "expected_net_pnl": expected_exit_net_pnl,
                        "reason": reason_str
                    })
                    self.last_exit_z_score = z_score
                    self.active_position = None
                    self.active_group_id = None
                    self.cooldown_ticks = 20
                    self.holding_ticks = 0
                    status = "CLOSED"

        return {
            "strategy": "Strategy_3_StatArb",
            "active": self.active_position is not None,
            "current_z_score": z_score,
            "status": status,
            "regime": regime,
            "signals": signals
        }


