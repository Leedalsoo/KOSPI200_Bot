import logging
import random
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class HistoricalReplayEngine:
    """
    [축 1] 가상 틱/호가 데이터 재생기 (Historical Replay Engine)
    - 역할: 과거 역사적 대폭락 장세 및 변동성 폭발 구간 틱을 재현하여 공급
    """
    def __init__(self) -> None:
        self.scenario_ticks: List[Dict[str, Any]] = []
        self.current_idx = 0
        self.is_active = False

    def load_scenario(self, scenario_name: str) -> None:
        """
        특정 과거 폭락장 및 변동성 폭발 시나리오 틱 로딩 모사
        """
        self.scenario_ticks.clear()
        self.current_idx = 0
        self.is_active = True
        
        # 1. 2020년 3월 코로나 팬데믹 서킷브레이커 폭락장 모사 시나리오 틱 생성
        if scenario_name == "COVID_PANIC_2020":
            logger.info("🎬 [REPLAY ENGINE] 2020년 3월 코로나 팬데믹 폭락장 시나리오 로딩...")
            base_price = 280.0
            for i in range(1, 501):
                vol_spike = 1.0 if i < 100 else (3.0 if i < 300 else 5.0)
                price_drop = 0.0 if i < 100 else (random.uniform(-1.5, -0.2) if i < 300 else random.uniform(-0.5, 0.5))
                base_price += price_drop
                
                self.scenario_ticks.append({
                    "seq": i,
                    "price": round(base_price, 2),
                    "active_vol": vol_spike,
                    "regime": "HIGH_VOL" if vol_spike > 2.0 else "NORMAL"
                })
        else:
            logger.warning("⚠️ [REPLAY ENGINE] 알 수 없는 시나리오 명칭: %s. 기본 모의 틱 모사로 대체합니다.", scenario_name)
            self.is_active = False

    def next_tick(self) -> Optional[Dict[str, Any]]:
        if not self.is_active or not self.scenario_ticks:
            return None
        
        if self.current_idx >= len(self.scenario_ticks):
            logger.info("🏁 [REPLAY ENGINE] 시나리오 틱 재생 완료.")
            self.is_active = False
            return None
            
        tick_data = self.scenario_ticks[self.current_idx]
        self.current_idx += 1
        return tick_data


class SlippageEngine:
    """
    [축 2] 가상 슬리피지와 체결 시뮬레이터 (Mock Broker & Slippage Engine)
    - 역할:
      1. 주문 수량, bidAskSpread, active_vol을 연동한 체결 오차 확률 모델링.
      2. 주문 방향에 따라 체결 가격 페널티 보정 (매수는 비싸게 가산, 매도는 싸게 감산).
      3. 가혹한 렉 상황을 모사하여 0.05pt ~ 0.50pt 범위 체결 오차 발생.
    """
    def __init__(self) -> None:
        logger.info("Slippage Engine (체결 밀림 확률 모델) initialized.")

    def apply_slippage(self, 
                       side: str, 
                       requested_price: float, 
                       qty: int, 
                       active_vol: float, 
                       spread: float) -> Dict[str, Any]:
        """
        체결가 슬리피지 및 지연 딜레이 연산
        """
        # 기본 슬리피지: 스프레드의 30% 수준
        base_slippage = spread * 0.3
        
        # 변동성 및 수량 비례 체결가 패널티 가산
        vol_impact = (active_vol - 1.0) * 0.08 if active_vol > 1.0 else 0.0
        qty_impact = (qty * 0.01)  # 대량 주문일수록 밀림 가중
        
        total_slippage = round(base_slippage + vol_impact + qty_impact + random.uniform(0.01, 0.05), 2)
        total_slippage = min(0.50, max(0.02, total_slippage))  # 0.02pt ~ 0.50pt 범위 락다운
        
        # 체결 지연 딜레이 (ms)
        delay_ms = int(50 + (active_vol * 80) + (qty * 5) + random.randint(10, 50))
        delay_ms = min(2000, delay_ms)  # 최대 2초 제한
        
        # 체결 가격 결정
        final_execution_price = requested_price
        if side == "BUY":
            final_execution_price += total_slippage
        elif side == "SELL":
            final_execution_price -= total_slippage
            
        final_execution_price = round(final_execution_price, 2)
        
        logger.info("📡 [SLIPPAGE ENGINE] 체결가 보정 집행 (%s) - 요청가: %.2f | 체결가: %.2f | 오차: -%.2fpt | 딜레이: %d ms",
                    side, requested_price, final_execution_price, total_slippage, delay_ms)
                    
        return {
            "execution_price": final_execution_price,
            "slippage_pts": total_slippage,
            "delay_ms": delay_ms
        }


class PaperTradingAccount:
    """
    [축 3] 페이퍼 트레이딩(Paper Trading) 모드 — 실시간 가상 구동 계정
    - 역할: 가상 계좌 장부 상태를 틱 단위로 관리하며 시스템 총 자산 평가
    """
    def __init__(self, initial_capital: float = 25000000.0):
        self.capital = initial_capital
        self.reserve = 0.0
        self.total_equity = initial_capital
        self.orders_history: List[Dict[str, Any]] = []
        logger.info("Paper Trading Account initialized with initial capital: ₩%s", f"{initial_capital:,.0f}")

    def update_equity(self, 
                      current_price: float, 
                      position_qty: int, 
                      portfolio_options: List[Dict[str, Any]], 
                      multiplier_futures: float = 250000.0, 
                      multiplier_options: float = 250000.0) -> float:
        """
        선물 포지션 평가 금액 및 옵션 평가 금액을 종합해 총자산 산출
        """
        futures_valuation = position_qty * current_price * multiplier_futures
        options_valuation = sum(
            int(pos.get("qty", 0)) * float(pos.get("price", 0.0)) * multiplier_options
            for pos in portfolio_options
        )
        self.total_equity = self.capital + self.reserve + futures_valuation + options_valuation
        return self.total_equity
