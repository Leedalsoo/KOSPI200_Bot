from decimal import Decimal
import logging
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from strategy.common import TradingDateResetHelper, ExecutionCostCalculator, WallClockTimer
from strategy.strategy_contract import StrategyContract

logger = logging.getLogger(__name__)

class Track3(StrategyContract):
    """
    [Track3] 통계적 차익거래 모듈 (Statistical Arbitrage / Pairs Trading)
    - 자본 배분: 5% (통계적 무위험 현금 알파 수취 모듈)
    - 역할: 
      1. 현선물 스프레드의 롤링 Z-Score 실시간 계산.
      2. 스프레드가 통계적 임계치(예: +-1.8 시그마)를 이탈할 때 스프레드 매도/매수 진입.
      3. 평균 회귀(Mean Reversion) 시점에 청산하여 무위험에 가까운 현금 알파 수취.
    """
    def __init__(self, config: Dict[str, Any]):
        self.params = config.get("strategies", {}).get("strategy_3", {}).get("params", {})
        self.z_entry_threshold = self.params.get("z_score_threshold", 1.8)
        self.z_exit_threshold = self.params.get("z_exit_threshold", 0.2)
        self.z_stop_loss_threshold = self.params.get("z_stop_loss_threshold", 3.5)  # 극단 이탈 손절
        self.max_holding_ticks = self.params.get("max_holding_ticks", 300)  # 타임아웃 청산
        
        # 내부 상태 관리
        self.active_position: Optional[str] = None  # "SHORT_SPREAD" 또는 "LONG_SPREAD" 또는 None
        self.cooldown_ticks = 0
        self.holding_ticks = 0
        self.date_reset_helper = TradingDateResetHelper()
        from typing import Dict
        from uuid import UUID
        self.pending_legs: Dict[UUID, Dict[str, Any]] = {}
        logger.info("Statistical Arbitrage Strategy (Track3) Initialized with 5% Capital Allocation.")

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
        from uuid import uuid4
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
        from uuid import uuid4
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
            # 모든 시세가 동일한 평탄 시계열인 경우 z_score = 0.0 (평균 회귀 상태로 판정)
            return 0.0, True
        
        current_spread = spread_series[-1]
        z_score = (current_spread - mean) / std
        return float(z_score), True


    def evaluate_arbitrage(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        [메인 통계 차익 평가 루틴]
        - 현선물 가격 데이터 및 최근 스프레드 시세를 받아 Z-Score를 분석하고 시그널 발행.
        - Track 3 전용 손익/수수료 스코프 우선 참조.
        """
        current_date = market_data.get("date_str", "UNKNOWN")
        if self.date_reset_helper.check_and_update(current_date):
            self.cooldown_ticks = 0
            self.holding_ticks = 0

        spread_history = market_data.get("spread_history", [])
        # 🛡️ [스코프 격리 및 None 방어] Track 3 전용 키 우선 참조
        raw_fees = market_data.get("track3_total_fees") if market_data.get("track3_total_fees") is not None else market_data.get("total_fees", 0.0)
        raw_pnl = market_data.get("track3_current_pnl") if market_data.get("track3_current_pnl") is not None else market_data.get("current_pnl", 0.0)
        total_fees: float = float(raw_fees or 0.0)
        current_pnl: float = float(raw_pnl or 0.0)

        
        z_score, is_valid = self.calculate_z_score(spread_history)
        
        # VKOSPI 변동성 연동 동적 Z-Score 진입 임계치 산정 (하드코딩 1.8 탈피)
        active_vol = float(market_data.get("active_vol", 1.0))
        base_vol = float(market_data.get("base_vol", 1.0))
        vol_ratio = active_vol / max(0.1, base_vol)
        effective_z_entry = max(1.5, self.z_entry_threshold * vol_ratio)

        signals = []
        status = "HOLD"
        
        if self.cooldown_ticks > 0:
            self.cooldown_ticks -= 1

        # 데이터가 무효(부족하거나 std==0)인 경우 억울한 조기 청산 방지 -> HOLD 고정
        if not is_valid:
            return {
                "strategy": "Strategy_3_StatArb",
                "active": self.active_position is not None,
                "current_z_score": 0.0,
                "status": "HOLD",
                "signals": []
            }

        # 1. 포지션이 없는 경우: 진입 조건 탐색 (Mid-Price 지정가 큐 방출)
        if self.active_position is None:
            time_str = market_data.get("time_str", "09:00:00")
            if time_str >= "15:15:00":
                return {
                    "strategy": "Strategy_3_StatArb",
                    "active": False,
                    "current_z_score": z_score,
                    "status": "CLOSE_CUTOFF_BLOCK",
                    "signals": []
                }

            if self.cooldown_ticks == 0:
                if z_score >= effective_z_entry:
                    self.active_position = "SHORT_SPREAD"
                    self.holding_ticks = 0
                    self._arb_high_pnl = 0.0
                    status = "ENTER_SHORT_SPREAD"
                    signals.append({
                        "action": "EXECUTE_STAT_ARB",
                        "type": "SHORT_SPREAD",
                        "z_score": z_score,
                        "pricing_mode": "MID_PRICE_OFFSET",
                        "limit_offset_ticks": 1,
                        "fallback_market_timeout_sec": 2.0,
                        "qty": 1,
                        "reason": f"Z-Score ({z_score:.2f}) exceeded dynamic threshold (+{effective_z_entry:.2f}). Selling spread via Limit Queue."
                    })
                elif z_score <= -effective_z_entry:
                    self.active_position = "LONG_SPREAD"
                    self.holding_ticks = 0
                    self._arb_high_pnl = 0.0
                    status = "ENTER_LONG_SPREAD"
                    signals.append({
                        "action": "EXECUTE_STAT_ARB",
                        "type": "LONG_SPREAD",
                        "z_score": z_score,
                        "pricing_mode": "MID_PRICE_OFFSET",
                        "limit_offset_ticks": 1,
                        "fallback_market_timeout_sec": 2.0,
                        "qty": 1,
                        "reason": f"Z-Score ({z_score:.2f}) breached dynamic threshold (-{effective_z_entry:.2f}). Buying spread via Limit Queue."
                    })

        # 2. 포지션을 보유 중인 경우: 3단계 동적 트레일링 스탑, 평균 회귀, 손절, 타임아웃, 장마감 강제 Flat 및 수수료 방어 탐색
        else:
            self.holding_ticks += 1
            
            # (0) 🛡️ [INTRADAY CUTOFF] 15:15:00 마감 윈도우 강제 Flat (오버나잇 갭 및 대규모 손실 방지)
            time_str = market_data.get("time_str", "09:00:00")
            if time_str >= "15:15:00":
                action_type = "CLOSE_SHORT_SPREAD" if self.active_position == "SHORT_SPREAD" else "CLOSE_LONG_SPREAD"
                signals.append({
                    "action": "CLOSE_STAT_ARB",
                    "type": action_type,
                    "z_score": z_score,
                    "qty": 1,
                    "reason": f"⏰ [INTRADAY CUTOFF] 장 마감(15:15) 도달로 Strategy 3 오버나잇 방지 강제 Flat 청산 (Hold ticks: {self.holding_ticks})"
                })
                self.active_position = None
                self.cooldown_ticks = 20
                self.holding_ticks = 0
                return {
                    "strategy": "Strategy_3_StatArb",
                    "active": False,
                    "current_z_score": z_score,
                    "status": "MARKET_CLOSE_FLATTEN",
                    "signals": signals
                }
            
            # (A) 3단계 동적 스케일링 트레일링 스탑 락인 평가
            prev_high = getattr(self, "_arb_high_pnl", 0.0)
            current_high = max(prev_high, current_pnl)
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

                if current_pnl <= stop_trigger_pnl:
                    action_type = "CLOSE_SHORT_SPREAD" if self.active_position == "SHORT_SPREAD" else "CLOSE_LONG_SPREAD"
                    signals.append({
                        "action": "CLOSE_STAT_ARB",
                        "type": action_type,
                        "pricing_mode": "PREEMPTIVE_STOP_LIMIT_QUEUE",
                        "limit_offset_ticks": 2,
                        "fallback_market_timeout_sec": 2.0,
                        "z_score": z_score,
                        "qty": 1,
                        "reason": f"🚀 [STAT ARB LOCK] High Watermark (KRW {current_high:,.0f}) 대비 {step_name} 반락. 선제 지정가 익절!"
                    })
                    self.active_position = None
                    self.cooldown_ticks = 20
                    self.holding_ticks = 0
                    return {"strategy": "Strategy_3_StatArb", "active": False, "status": "TRAILING_PROFIT_LOCK", "signals": signals}

            # (B) Z-Score 극단 이탈 손절 판정
            is_stop_loss = False
            if self.active_position == "SHORT_SPREAD" and z_score >= self.z_stop_loss_threshold:
                is_stop_loss = True
            elif self.active_position == "LONG_SPREAD" and z_score <= -self.z_stop_loss_threshold:
                is_stop_loss = True

            # (C) 최대 보유시간 타임아웃 판정
            is_timeout = (self.holding_ticks >= self.max_holding_ticks)

            if is_stop_loss:
                reason_str = f"Z-Score extreme breach ({z_score:.2f} >= {self.z_stop_loss_threshold}). Stop loss triggered."
                action_type = "CLOSE_SHORT_SPREAD" if self.active_position == "SHORT_SPREAD" else "CLOSE_LONG_SPREAD"
                signals.append({
                    "action": "CLOSE_STAT_ARB",
                    "type": action_type,
                    "z_score": z_score,
                    "qty": 1,
                    "reason": reason_str
                })
                self.active_position = None
                self.cooldown_ticks = 40  # 손절 후 40틱 쿨다운
                self.holding_ticks = 0
                status = "STOP_LOSS"

            elif is_timeout:
                reason_str = f"Holding time limit reached ({self.holding_ticks} ticks >= {self.max_holding_ticks}). Timeout exit."
                action_type = "CLOSE_SHORT_SPREAD" if self.active_position == "SHORT_SPREAD" else "CLOSE_LONG_SPREAD"
                signals.append({
                    "action": "CLOSE_STAT_ARB",
                    "type": action_type,
                    "z_score": z_score,
                    "qty": 1,
                    "reason": reason_str
                })
                self.active_position = None
                self.cooldown_ticks = 20
                self.holding_ticks = 0
                status = "TIMEOUT_EXIT"

            elif self.active_position == "SHORT_SPREAD" and z_score <= self.z_exit_threshold:
                reason_str = f"Z-Score returned to mean ({z_score:.2f})."
                signals.append({
                    "action": "CLOSE_STAT_ARB",
                    "type": "CLOSE_SHORT_SPREAD",
                    "pricing_mode": "MID_PRICE_OFFSET",
                    "limit_offset_ticks": 1,
                    "z_score": z_score,
                    "qty": 1,
                    "reason": reason_str
                })
                self.active_position = None
                self.cooldown_ticks = 20
                self.holding_ticks = 0
                status = "CLOSED"

            elif self.active_position == "LONG_SPREAD" and z_score >= -self.z_exit_threshold:
                reason_str = f"Z-Score returned to mean ({z_score:.2f})."
                signals.append({
                    "action": "CLOSE_STAT_ARB",
                    "type": "CLOSE_LONG_SPREAD",
                    "pricing_mode": "MID_PRICE_OFFSET",
                    "limit_offset_ticks": 1,
                    "z_score": z_score,
                    "qty": 1,
                    "reason": reason_str
                })
                self.active_position = None
                self.cooldown_ticks = 20
                self.holding_ticks = 0
                status = "CLOSED"

        return {
            "strategy": "Strategy_3_StatArb",
            "active": self.active_position is not None,
            "current_z_score": z_score,
            "status": status,
            "signals": signals
        }

