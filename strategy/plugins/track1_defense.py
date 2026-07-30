import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class DetailedProductionFenceEngine:
    """
    [전략 1: 꼬리표 순환형 다이내믹 가두리 및 미아 포지션 선물 헷지 루프]
    공방 일체형 펜스 엔진.
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
        self.last_trading_date = None

    def evaluate_strategy(self, current_underlying: float, current_atm: float, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """서버 연동 브릿지 함수"""
        signals = []
        current_date = market_data.get("date_str", "UNKNOWN")
        trend_signal = market_data.get("momentum_confirmed", True) 

        # 날짜 변경 감지
        if self.last_trading_date != current_date:
            self.last_trading_date = current_date
            self.futures_hedge_count = 0

        # 장 개장 세팅 (1번 꼬리표)
        if not self.is_market_opened:
            self.base_price = current_atm
            self.is_market_opened = True
            open_signals = self.on_market_open(current_underlying)
            signals.extend(open_signals)
            
        # 틱 메인 루프
        tick_signals = self.on_tick(current_underlying, trend_signal)
        signals.extend(tick_signals)
        
        return {"signals": signals}

    def on_market_open(self, current_price: float) -> List[Dict]:
        """[1단계] 장 시작 직후 넓은 양매수 선제 구축 및 초기 풋매도 가두리 형성"""
        signals = []
        call_strike = round((current_price + self.fence_distance)/2.5)*2.5
        put_strike = round((current_price - self.fence_distance)/2.5)*2.5
        
        self.long_strangle_positions.append({'type': 'CALL', 'strike': call_strike, 'qty': 1})
        self.long_strangle_positions.append({'type': 'PUT', 'strike': put_strike, 'qty': 1})
        
        signals.append({
            "action": "TAIL_DEFENSE_BUILD",
            "call_strike": call_strike,
            "put_strike": put_strike,
            "reason": "[장 시작 세팅] 넓은 양매수(Long Strangle) 구축 완료"
        })
        
        # 하방(풋매도) 가두리 구축
        self.active_fence = {'type': 'PUT', 'strike': put_strike, 'tag_id': 1}
        
        signals.append({
            "action": "FENCE_BUILD",
            "type": "PUT",
            "strike": put_strike,
            "tag_id": 1,
            "reason": f"초기 풋매도 가두리 (행사가: {put_strike}, #1)"
        })
        
        logger.info(f"[장 시작 통합 세팅] 넓은 양매수 구축 완료 | 초기 풋매도 가두리 행사가: {put_strike} (#1)")
        return signals

    def on_tick(self, current_price: float, trend_signal: bool) -> List[Dict]:
        """[2단계] 틱 스트리밍 루프: 꼬리표 순환 및 미아 방어 헷지"""
        signals = []
        if not self.active_fence:
            return signals

        # [시나리오 A] 상대방 90% 도달 시 순환 (이익 확정)
        if self.check_opposite_90_reached(current_price):
            signals.extend(self.execute_fence_rotation(current_price))
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
            else:
                signals.extend(self.check_hedge_exit_conditions(current_price))
                
        return signals

    def check_opposite_90_reached(self, current_price: float) -> bool:
        target_90_dist = self.fence_distance * 0.9
        if self.active_fence['type'] == 'PUT':
            target_90_price = self.base_price + target_90_dist
            return current_price >= target_90_price
        else:
            target_90_price = self.base_price - target_90_dist
            return current_price <= target_90_price

    def check_returning_90_approaching(self, current_price: float) -> bool:
        warning_dist = self.fence_distance * 0.9
        if self.active_fence['type'] == 'PUT':
            return current_price <= (self.base_price - warning_dist)
        else:
            return current_price >= (self.base_price + warning_dist)

    def execute_fence_rotation(self, current_price: float) -> List[Dict]:
        """[꼬리표 순환 루프] 매수 청산 + 반대편 신규 매도"""
        signals = []
        old_tag = self.active_fence['tag_id']
        old_type = self.active_fence['type']
        old_strike = self.active_fence['strike']
        
        realized_profit = 2.5 * 50000 
        self.profit_buffer += realized_profit
        
        logger.info(f"🔄 [순환 루프] 꼬리표 #{old_tag} 청산 | 버퍼 누적: {self.profit_buffer}원")
        signals.append({
            "action": "FENCE_CLEAR",
            "type": old_type,
            "strike": old_strike,
            "tag_id": old_tag,
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
            "reason": f"신규 꼬리표 #{old_tag + 1} ({new_type})"
        })
        logger.info(f"🏗️ [신규 가두리] {new_type}매도 (행사가: {new_strike}, #{old_tag + 1})")
        return signals

    def check_hedge_exit_conditions(self, current_price: float) -> List[Dict]:
        signals = []
        fence_strike = self.active_fence['strike']
        
        # 3단계: 100% 격돌 (선물+옵션 전량 청산)
        is_flatten = False
        if self.active_fence['type'] == 'PUT' and current_price <= fence_strike:
            is_flatten = True
        elif self.active_fence['type'] == 'CALL' and current_price >= fence_strike:
            is_flatten = True
            
        if is_flatten:
            logger.critical("💥 [100% 격돌] 방어선 붕괴. 선물 및 가두리 전량 동시 청산(Flatten)")
            signals.append({"action": "FLATTEN_ALL", "reason": "100% 방어선 격돌"})
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
            signals.append({
                "action": "FUTURES_UNWIND",
                "type": self.active_hedge,
                "reason": "1.5pt 반전 휩소 탈출"
            })
            self.active_hedge = None

        return signals

