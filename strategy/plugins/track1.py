from decimal import Decimal
import logging
from typing import Dict, Any, List, Optional
from strategy.common import TradingDateResetHelper, ExecutionCostCalculator, WallClockTimer

logger = logging.getLogger(__name__)

class Track1:
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
        tick_signals = self.on_tick(current_underlying, trend_signal, days_to_expiry)
        signals.extend(tick_signals)
        
        return {"signals": signals}

    def on_market_open(self, current_price: float) -> List[Dict]:
        """[1단계] 장 시작 직후 넓은 양매수 선제 구축 및 초기 풋매도 가두리 형성"""
        signals = []
        self.base_price = current_price
        call_strike = round((current_price + self.fence_distance)/2.5)*2.5
        put_strike = round((current_price - self.fence_distance)/2.5)*2.5
        
        self.long_strangle_positions.append({'type': 'CALL', 'strike': call_strike, 'qty': 1})
        self.long_strangle_positions.append({'type': 'PUT', 'strike': put_strike, 'qty': 1})
        
        signals.append({
            "action": "TAIL_DEFENSE_BUILD",
            "call_strike": call_strike,
            "put_strike": put_strike,
            "qty": 1,
            "reason": "[장 시작 세팅] 넓은 양매수(Long Strangle) 구축 완료"
        })
        
        # 하방(풋매도) 가두리 구축
        self.active_fence = {'type': 'PUT', 'strike': put_strike, 'tag_id': 1}
        
        signals.append({
            "action": "FENCE_BUILD",
            "type": "PUT",
            "strike": put_strike,
            "tag_id": 1,
            "qty": 1,
            "reason": f"초기 풋매도 가두리 (행사가: {put_strike}, #1)"
        })
        
        logger.info(f"[장 시작 통합 세팅] 넓은 양매수 구축 완료 | 초기 풋매도 가두리 행사가: {put_strike} (#1)")
        return signals

    def on_tick(self, current_price: float, trend_signal: bool, days_to_expiry: float = 30.0) -> List[Dict]:
        """[2단계] 틱 스트리밍 루프: 꼬리표 순환, 미아 방어 헷지 및 만기 D-4 롱 공격 전환"""
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
                "reason": "만기 D-4 시간가치 소멸 가두리 매도 조기 청산 (양매수 롱 공격 유지)"
            })
            self.active_fence = None
            return signals

        if not self.active_fence or days_to_expiry <= 4.0:
            return signals

        # 100% 격돌 및 1.5pt 반전 매 틱 독립 우선 체크 (갭 대응)
        hedge_exit_signals = self.check_hedge_exit_conditions(current_price)
        if hedge_exit_signals:
            signals.extend(hedge_exit_signals)
            return signals

        # [시나리오 A] 상대방 90% 도달 시 순환 (이익 확정)
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
                    "reason": f"선물 헷지 #{self.futures_hedge_count} 발동"
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
            "reason": f"꼬리표 #{old_tag} 순환 청산"
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
            "reason": f"신규 꼬리표 #{old_tag + 1} ({new_type})"
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
        if self.active_fence['type'] == 'PUT' and current_price <= fence_strike:
            is_flatten = True
        elif self.active_fence['type'] == 'CALL' and current_price >= fence_strike:
            is_flatten = True
            
        if is_flatten:
            logger.critical("💥 [100% 격돌] 방어선 붕괴. 해당 가두리 옵션 및 선물 헷지 청산")
            old_tag = self.active_fence['tag_id']
            old_type = self.active_fence['type']
            old_strike = self.active_fence['strike']
            
            # 1. 100% 도달한 가두리 매도 옵션 청산
            signals.append({
                "action": "FENCE_CLEAR",
                "type": old_type,
                "strike": old_strike,
                "tag_id": old_tag,
                "qty": 1,
                "reason": f"100% 방어선 격돌 가두리 #{old_tag} 청산"
            })
            
            # 2. 헷징 선물 포지션 청산 (선물 반대 매매)
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


