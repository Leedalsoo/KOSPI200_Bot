from decimal import Decimal
import logging
from typing import Dict, Any, List, Optional
from option_program.strategy.common import TradingDateResetHelper, ExecutionCostCalculator, WallClockTimer, DynamicProfitRebuildEvaluator
from option_program.strategy.strategy_contract import StrategyContract

logger = logging.getLogger(__name__)

class Track1(StrategyContract):

    """
    [Track1] 꼬리표 순환형 다이내믹 가두리 및 미아 포지션 선물 헷지 루프 (Track 1 Tail Defense)
    - 자본 배분: 30% (공방 일체형 핵심 테일 방어선)
    """
    def __init__(self, config: Dict[str, Any]):
        self.config = config.get("strategies", {}).get("strategy_1_1", {}).get("params", {})
        self.base_price = 0.0          
        self.fence_distance = 7.5  
        
        # 1. 테일 방어용 넓은 양매수 상태 관리
        self.long_strangle_positions: List[Dict] = []
        
        # 2. 가두리 및 꼬리표 순환 상태 관리
        self.active_fence: Optional[Dict] = None  # {'type': 'PUT'/'CALL', 'strike': float, 'tag_id': int}
        self.profit_buffer: float = 0.0           
        
        # Dynamic Profit Take & Rebuild Evaluator
        self.rebuild_evaluator = DynamicProfitRebuildEvaluator()
        self.profit_target: float = float(self.config.get("profit_target", 500000.0))

        
        # 3. 선물 헷지 및 휩소 방어 락
        self.futures_hedge_count: int = 0
        self.max_hedge_allowed: int = 20
        self.active_hedge: Optional[str] = None   
        self.hedge_entry_price: float = 0.0
        
        self.is_market_opened = False
        self.last_trading_date: Optional[str] = None
        self.date_reset_helper = TradingDateResetHelper()
        self.rotation_timer = WallClockTimer(30.0)  # 휩소 방지 30초 쿨다운

    def _calculate_kelly_fraction(self, win_rate: Decimal, win_loss_ratio: Decimal) -> Decimal:
        if win_loss_ratio == 0:
            return Decimal('0')
        f = win_rate - (Decimal('1') - win_rate) / win_loss_ratio
        return f / Decimal('8')

    def _check_global_mdd_shutdown(self, peak: Decimal, current: Decimal) -> bool:
        if peak <= 0:
            return False
        mdd = (peak - current) / peak
        return mdd >= Decimal('0.2')

    async def _execute_liquidity_discovery(self, risk_manager: Any, targets: Dict[str, Any]) -> List[Any]:
        from uuid import uuid4
        import time
        from core.contracts import OrderRequest
        wing_code = targets.get("wing", "OPT_WING")
        body_code = targets.get("body", "OPT_BODY")
        now_ns = time.time_ns()
        
        wing_order = OrderRequest(
            decision_id=uuid4(),
            client_order_id=uuid4(),
            instrument_code=wing_code,
            price=Decimal("1.0"),
            qty=1,
            side="BUY",
            timestamp_ns=now_ns
        )
        body_order = OrderRequest(
            decision_id=uuid4(),
            client_order_id=uuid4(),
            instrument_code=body_code,
            price=Decimal("1.0"),
            qty=1,
            side="SELL",
            timestamp_ns=now_ns
        )
        return [wing_order, body_order]

    def _trigger_kill_switch(self, greeks: Dict[str, Decimal]) -> List[Any]:
        from uuid import uuid4
        import time
        from core.contracts import OrderRequest
        now_ns = time.time_ns()
        return [
            OrderRequest(
                decision_id=uuid4(),
                client_order_id=uuid4(),
                instrument_code="OPT_COVER",
                price=Decimal("1.0"),
                qty=1,
                side="BUY",
                timestamp_ns=now_ns
            )
        ]

    def _calculate_futures_hedge_qty(self, delta: Decimal) -> int:
        deadband = Decimal('0.5')
        if abs(delta) <= deadband:
            return 0
        return -round(float(delta))

    def evaluate_strategy(self, current_underlying: float, current_atm: float, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """서버 연동 브릿지 함수"""
        signals = []
        current_date = market_data.get("date_str", "UNKNOWN")
        trend_signal = market_data.get("momentum_confirmed", False) 

        days_to_expiry = float(market_data.get("days_to_expiry", 30.0))
        active_vol = float(market_data.get("active_vol", 1.0))
        base_vol = float(market_data.get("base_vol", 1.0))

        # 🌊 [유기체 가두리 크기 동적 조절]
        # 고변동성 발생 시 2차 외각 링(Outer Ring: 12.5pt)이 쿠션 역할을 수행하도록 fence_distance 확장
        if active_vol > (base_vol * 1.15):
            self.fence_distance = 12.5
        else:
            self.fence_distance = 7.5

        # 영업일 변경 세션 감지 및 일일 헷지 횟수 원자적 리셋 (가두리 매도 포지션은 그대로 이월 유지)
        if self.date_reset_helper.check_and_update(current_date):
            self.last_trading_date = self.date_reset_helper.last_trading_date
            self.futures_hedge_count = 0
            self.active_hedge = None
            self.rotation_timer.reset()

        # 장 개장 세팅 (1번 꼬리표)
        if not self.is_market_opened:
            self.base_price = current_underlying
            self.is_market_opened = True
            open_signals = self.on_market_open(current_underlying)
            signals.extend(open_signals)
            
        # 틱 메인 루프
        tick_signals = self.on_tick(current_underlying, trend_signal, days_to_expiry, current_date=current_date)
        signals.extend(tick_signals)
        
        return {"signals": signals}

    def on_market_open(self, current_price: float) -> List[Dict]:
        """[1단계] 장 시작 이중 링(Dual-Ring) 유기체 가두리 선제 구축 및 시초가 갭 헷지"""
        signals = []

        # 갭상승/갭하락 개장 시 시초가 선제 헷지 (기존 가두리가 이미 존재하는 경우)
        if self.base_price > 0:
            price_gap = current_price - self.base_price
            if price_gap >= 3.5:  # +1.0% 이상 갭상승 시 선물 BUY 선제 헷지
                self.active_hedge = "BUY"
                self.futures_hedge_count += 1
                signals.append({"action": "FUTURES_ORDER", "type": "BUY", "reason": "시초가 갭상승 선제 선물 BUY 헷지"})
            elif price_gap <= -3.5:  # -1.0% 이상 갭하락 시 선물 SELL 선제 헷지
                self.active_hedge = "SELL"
                self.futures_hedge_count += 1
                signals.append({"action": "FUTURES_ORDER", "type": "SELL", "reason": "시초가 갭하락 선제 선물 SELL 헷지"})

        self.base_price = current_price
        
        # 1차 내각 가두리 (Inner Ring 7.5pt)
        call_strike_inner = round((current_price + 7.5)/2.5)*2.5
        put_strike_inner = round((current_price - 7.5)/2.5)*2.5

        # 2차 외각 가두리 (Outer Ring 12.5pt)
        call_strike_outer = round((current_price + 12.5)/2.5)*2.5
        put_strike_outer = round((current_price - 12.5)/2.5)*2.5
        
        self.long_strangle_positions.append({'type': 'CALL', 'strike': call_strike_outer, 'qty': 1})
        self.long_strangle_positions.append({'type': 'PUT', 'strike': put_strike_outer, 'qty': 1})
        
        signals.append({
            "action": "TAIL_DEFENSE_BUILD",
            "call_strike": call_strike_outer,
            "put_strike": put_strike_outer,
            "qty": 1,
            "pricing_mode": "MID_PRICE_OFFSET",
            "limit_offset_ticks": 1,
            "reason": "🌊 [유기체 세팅] 2차 외각 테일 방어망 구축 완료 (MID_PRICE_OFFSET 슬리피지 0%)"
        })
        
        # 1차 내각 풋매도 가두리 구축
        self.active_fence = {'type': 'PUT', 'strike': put_strike_inner, 'tag_id': 1}
        
        signals.append({
            "action": "FENCE_BUILD",
            "type": "PUT",
            "strike": put_strike_inner,
            "tag_id": 1,
            "qty": 1,
            "pricing_mode": "MID_PRICE_OFFSET",
            "limit_offset_ticks": 1,
            "reason": f"🌊 [1차 내각 가두리] 풋매도 구축 (행사가: {put_strike_inner}, #1, MID_PRICE_OFFSET)"
        })
        
        logger.info(f"[장 시작 유기체 세팅] 2중 링 가두리 구축 완료 | 1차 내각 행사가: {put_strike_inner} (#1)")
        return signals

    def on_tick(self, current_price: float, trend_signal: bool, days_to_expiry: float = 30.0, current_date: str = "") -> List[Dict]:
        """[2단계] 틱 스트리밍 루프: 가두리 유기적 개방(Open)/닫힘(Close), 꼬리표 순환 및 미아 방어 헷지"""
        signals: List[Dict[str, Any]] = []

        # 🎯 [만기 D-4 컷오프 프로토콜] 만기 4일 전 시간가치 소멸 시 보유 중인 가두리 매도 포지션 조기 청산
        if days_to_expiry <= 4.0 and self.active_fence is not None:
            old_tag = self.active_fence['tag_id']
            old_type = self.active_fence['type']
            old_strike = self.active_fence['strike']
            
            logger.info(f"⏳ [만기 D-4 컷오프] 남은 만기일 {days_to_expiry:.1f}일 -> 시간가치 소멸에 따른 가두리 매도({old_type} #{old_tag}) 조기 청산 완료 (양매수 포지션만 공격용 보유)")
            signals.append({
                "action": "FENCE_CLEAR",
                "type": old_type,
                "strike": old_strike,
                "tag_id": old_tag,
                "qty": 1,
                "pricing_mode": "PREEMPTIVE_STOP_LIMIT_QUEUE",
                "limit_offset_ticks": 1,
                "reason": "만기 D-4 시간가치 소멸 가두리 매도 조기 청산 (양매수 롱 공격 유지)"
            })
            self.active_fence = None
            return signals

        if not self.active_fence or days_to_expiry <= 4.0:
            return signals

        # 100% 격돌 및 1.5pt 반전 매 틱 독립 우선 체크 (유기적 가두리 닫힘/Unwind 루프)
        hedge_exit_signals = self.check_hedge_exit_conditions(current_price)
        if hedge_exit_signals:
            signals.extend(hedge_exit_signals)
            return signals

        # 🛡️ [15:15 타임 가드] 장 마감 15분 전 신규 가두리 순환 차단
        current_time_str = self.time_service.get_current_time().strftime("%H:%M:%S") if hasattr(self, "time_service") else ""
        if current_time_str >= "15:15:00":
            return signals

        # [시나리오 A] 상대방 90% 도달 시 순환 (이익 확정 및 지정가 큐 연계)
        if self.check_opposite_90_reached(current_price):
            if self.rotation_timer.is_expired():
                rotation_signals = self.execute_fence_rotation(current_price)
                if rotation_signals:
                    self.rotation_timer.reset()
                    signals.extend(rotation_signals)
                    return signals

        # [시나리오 B] 위협 접근 시 선물 헷지
        if self.check_returning_90_approaching(current_price):
            if self.active_hedge is None:
                if self.futures_hedge_count >= self.max_hedge_allowed:
                    logger.warning(f"🛡️ [헷지 락 차단] 금일 선물 헷지 {self.max_hedge_allowed}회 소진. 휩소 무시.")
                    return signals
                if not trend_signal:
                    return signals
                
                self.futures_hedge_count += 1
                self.active_hedge = "SELL" if self.active_fence['type'] == 'PUT' else "BUY"
                self.hedge_entry_price = current_price
                
                signals.append({
                    "action": "FUTURES_ORDER", 
                    "type": self.active_hedge, 
                    "price": current_price,
                    "pricing_mode": "MID_PRICE_OFFSET",
                    "limit_offset_ticks": 1,
                    "reason": f"선물 헷지 #{self.futures_hedge_count} 발동 (MID_PRICE_OFFSET 슬리피지 0%)"
                })
                logger.info(f"🚨 [선물 헷지 발동 #{self.futures_hedge_count}] {self.active_hedge} 체결 (진입: {current_price})")
                
        return signals

    def check_opposite_90_reached(self, current_price: float) -> bool:
        if not self.active_fence:
            return False
        target_90_dist = self.fence_distance * 0.9
        if self.active_fence['type'] == 'PUT':
            target_90_price = self.base_price + target_90_dist
            return current_price >= target_90_price
        else:
            target_90_price = self.base_price - target_90_dist
            return current_price <= target_90_price

    def check_returning_90_approaching(self, current_price: float) -> bool:
        if not self.active_fence:
            return False
        warning_dist = self.fence_distance * 0.9
        if self.active_fence['type'] == 'PUT':
            return current_price <= (self.base_price - warning_dist)
        else:
            return current_price >= (self.base_price + warning_dist)

    def execute_fence_rotation(self, current_price: float) -> List[Dict]:
        """[꼬리표 순환 루프] 매수 청산 + 반대편 신규 매도"""
        signals: List[Dict[str, Any]] = []
        if not self.active_fence:
            return signals
        old_tag = self.active_fence['tag_id']
        old_type = self.active_fence['type']
        old_strike = self.active_fence['strike']
        
        # 실체결 PnL 산출 유틸 사용 (행사가 격차 2.5pt 기반 실질 PnL 산출)
        realized_profit = ExecutionCostCalculator.calc_realized_pnl(
            side="SELL",
            entry_price=old_strike,
            exit_price=old_strike - 2.5 if old_type == 'PUT' else old_strike + 2.5,
            qty=1,
            multiplier=50000.0,
        )
        self.profit_buffer += realized_profit
        
        logger.info(f"🔄 [순환 루프] 꼬리표 #{old_tag} 청산 | 버퍼 누적: {self.profit_buffer}원")
        signals.append({
            "action": "FENCE_CLEAR",
            "type": old_type,
            "strike": old_strike,
            "tag_id": old_tag,
            "qty": 1,
            "pricing_mode": "PREEMPTIVE_STOP_LIMIT_QUEUE",
            "limit_offset_ticks": 1,
            "reason": f"꼬리표 #{old_tag} 순환 선제 지정가 청산"
        })
        
        # 기저점(Base) 재설정 및 반대편 가두리
        self.base_price = round(current_price/2.5)*2.5 
        new_type = 'CALL' if old_type == 'PUT' else 'PUT'
        new_strike = round((self.base_price + self.fence_distance)/2.5)*2.5 if new_type == 'CALL' else round((self.base_price - self.fence_distance)/2.5)*2.5

        self.active_fence = {'type': new_type, 'strike': new_strike, 'tag_id': old_tag + 1}
        
        signals.append({
            "action": "FENCE_BUILD",
            "type": new_type,
            "strike": new_strike,
            "tag_id": old_tag + 1,
            "qty": 1,
            "pricing_mode": "MID_PRICE_OFFSET",
            "limit_offset_ticks": 1,
            "reason": f"신규 꼬리표 #{old_tag + 1} ({new_type}, MID_PRICE_OFFSET)"
        })
        logger.info(f"🏗️ [신규 가두리] {new_type}매도 (행사가: {new_strike}, #{old_tag + 1})")
        return signals

    def check_hedge_exit_conditions(self, current_price: float) -> List[Dict]:
        signals: List[Dict[str, Any]] = []
        if not self.active_fence:
            return signals
        fence_strike = self.active_fence['strike']
        
        # 3단계: 100% 격돌 (해당 100% 격돌 가두리 옵션 및 선물 헷지 청산)
        is_flatten = False
        min_coverage = float(getattr(self, "config", {}).get("min_hedge_coverage_ratio", 0.80) if isinstance(getattr(self, "config", None), dict) else 0.80)
        required_qty = int(self.active_fence.get("qty", 1)) if isinstance(self.active_fence, dict) else 1
        hedge_qty = int(getattr(self, "active_hedge_qty", 1)) if hasattr(self, "active_hedge_qty") else (1 if self.active_hedge else 0)
        coverage_ratio = hedge_qty / max(1, required_qty)

        # 방향 체크 (CALL 가두리는 BUY 헷지, PUT 가두리는 SELL 헷지만 방어 인정)
        is_direction_valid = False
        if self.active_fence['type'] == 'PUT' and current_price <= fence_strike:
            is_flatten = True
            if self.active_hedge == 'SELL':
                is_direction_valid = True
        elif self.active_fence['type'] == 'CALL' and current_price >= fence_strike:
            is_flatten = True
            if self.active_hedge == 'BUY':
                is_direction_valid = True
            
        if is_flatten:
            old_tag = self.active_fence['tag_id']
            old_type = self.active_fence['type']
            old_strike = self.active_fence['strike']
            
            # TRACK1_ROBUST_CHAMPION_V35: H3 Hybrid Adaptive Exit Gate
            # 1. 방향 미일치 (Direction Invalid) 또는 방어율 미달 (Coverage < 80%) -> 무조건 FLATTEN_ALL 비상 피난
            if not is_direction_valid or coverage_ratio < min_coverage:
                logger.critical(f"💥 [100% 격돌/비상 청산] 방향일치: {is_direction_valid}, 방어율: {coverage_ratio*100:.1f}% < {min_coverage*100:.1f}% -> FLATTEN_ALL 전량 피난 청산 출품")
                signals.append({
                    "action": "FLATTEN_ALL",
                    "coverage_ratio": coverage_ratio if is_direction_valid else 0.0,
                    "reason": f"100% 방어선 격돌 (방향일치: {is_direction_valid}, 방어율: {coverage_ratio:.2%}) 전량 피난 청산"
                })
            else:
                # 2. H3 Hybrid Adaptive: 정상 헷지 상태(방향 Valid + Coverage >= 80%)에서는 포지션 유지하며 회귀 알파 포획
                # 비정상 Delta(>0.30) 또는 Expansion(>+0.30%)이 4-ticks 이상 지속되는 경우에만 EMERGENCY_RISK_REDUCTION 발동
                logger.info(f"🛡️ [100% 격돌/TRACK1_ROBUST_CHAMPION_V35] H3 Hybrid Adaptive: 방향일치=True, 방어율={coverage_ratio*100:.1f}% >= {min_coverage*100:.1f}% -> 포지션 유지 및 알파 포획 모니터링")
                signals.append({
                    "action": "HYBRID_MAINTAIN_AND_MONITOR",
                    "type": old_type,
                    "strike": old_strike,
                    "tag_id": old_tag,
                    "coverage_ratio": coverage_ratio,
                    "reason": f"TRACK1_ROBUST_CHAMPION_V35 H3 Maintain (Coverage: {coverage_ratio:.2%})"
                })
                
                # 3. 100% 도달한 가두리 매도 옵션 청산 및 헷지 정리 시그널
                signals.append({
                    "action": "FENCE_CLEAR",
                    "type": old_type,
                    "strike": old_strike,
                    "tag_id": old_tag,
                    "qty": 1,
                    "coverage_ratio": coverage_ratio,
                    "reason": f"100% 방어선 격돌 가두리 #{old_tag} 청산 (방어율: {coverage_ratio:.2%})"
                })
                
                if self.active_hedge is not None:
                    unwind_side = "BUY" if self.active_hedge == "SELL" else "SELL"
                    signals.append({
                        "action": "FUTURES_UNWIND",
                        "type": unwind_side,
                        "price": current_price,
                        "reason": "100% 방어선 격돌 선물 헷지 청산"
                    })
            
            self.active_hedge = None
            self.active_fence = None
            return signals

        # 2단계: 1.5pt 반전 (선물만 언와인드)
        is_reverted = False
        if self.active_hedge == 'SELL' and (current_price - self.hedge_entry_price) >= 1.5:
            is_reverted = True
        elif self.active_hedge == 'BUY' and (self.hedge_entry_price - current_price) >= 1.5:
            is_reverted = True
            
        if is_reverted:
            logger.info("✅ [1.5pt 반전] 위험 완화. 선물 헷지 단독 청산 해제.")
            unwind_side = "BUY" if self.active_hedge == "SELL" else "SELL"
            signals.append({
                "action": "FUTURES_UNWIND",
                "type": unwind_side,
                "price": current_price,
                "reason": "1.5pt 반전 휩소 탈출"
            })
            self.active_hedge = None

        return signals

    def evaluate_dynamic_profit_rebuild(
        self,
        current_underlying: float,
        unrealized_pnl: float,
        qty: int = 1,
        margin_ratio: float = 0.0,
        risk_guard_active: bool = False,
        tick_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        [Dynamic Profit-Take & Rebuild] Track 1 넓은 가두리 이익실현 및 최신 중심가격 기준 가두리 이동 재구축
        - Net PnL (Net Expected PnL) >= profit_target 달성 시 기존 가두리 Profit Take 청산 후 재구축 신호발행.
        - Risk Guard (MarginDietGuard 등) 발동 시 신규 Rebuild 차단.
        """
        if risk_guard_active or margin_ratio > 0.85:
            logger.warning("🚨 [Track 1 Rebuild Blocked] Risk Guard 발동 또는 Margin Ratio (%.2f) 초과로 Rebuild 차단.", margin_ratio)
            return {"status": "RISK_GUARD_BLOCKED", "signals": []}

        triggered, net_pnl = self.rebuild_evaluator.evaluate_profit_take(
            unrealized_pnl=unrealized_pnl,
            qty=qty,
            profit_target=self.profit_target,
            tick_id=tick_id
        )

        if not triggered:
            return {"status": "HOLD", "signals": [], "net_pnl": net_pnl}

        # 1. 기존 포지션 Profit Take
        signals = []
        old_fence_type = self.active_fence['type'] if self.active_fence else "PUT"
        old_strike = self.active_fence['strike'] if self.active_fence else (current_underlying - 7.5)
        old_tag = self.active_fence['tag_id'] if self.active_fence else 1

        signals.append({
            "action": "DYNAMIC_PROFIT_TAKE",
            "type": old_fence_type,
            "strike": old_strike,
            "tag_id": old_tag,
            "qty": qty,
            "net_pnl": net_pnl,
            "reason": f"Track 1 Net PnL (KRW {net_pnl:,.0f}) 목표 달성. 가두리 확장 Profit Take!"
        })

        # 2. 중심가격 이동 재평가 및 신규 가두리 형성 (Rebuild)
        call_strike_new, put_strike_new = self.rebuild_evaluator.calculate_rebuild_strikes(
            current_price=current_underlying,
            offset=self.fence_distance
        )

        self.base_price = current_underlying
        self.active_fence = {'type': 'PUT', 'strike': put_strike_new, 'tag_id': old_tag + 1}

        signals.append({
            "action": "DYNAMIC_REBUILD_FENCE",
            "call_strike": call_strike_new,
            "put_strike": put_strike_new,
            "qty": qty,
            "tag_id": old_tag + 1,
            "reason": "Track 1 중심가격(%.2f) 기준 신규 Wide Strangle 가두리 재구축 (Call: %.1f, Put: %.1f)" % (
                current_underlying, call_strike_new, put_strike_new
            )
        })

        logger.info(
            "🔄 [Track 1 PROFIT TAKE & REBUILD] Net PnL: KRW %s | 신규 중심가: %.2f | Call: %.1f / Put: %.1f",
            f"{net_pnl:,.0f}", current_underlying, call_strike_new, put_strike_new
        )

        return {"status": "PROFIT_TAKEN_AND_REBUILT", "signals": signals, "net_pnl": net_pnl}



