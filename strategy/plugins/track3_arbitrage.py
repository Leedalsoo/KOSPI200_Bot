import logging
import numpy as np
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class StatisticalArbitrageStrategy:
    """
    [전략 3] 통계적 차익거래 모듈 (Statistical Arbitrage / Pairs Trading)
    - 자본 배분: 40% (시스템의 캐시카우 및 1순위 제어권)
    - 역할: 
      1. 현선물 스프레드의 롤링 Z-Score 실시간 계산.
      2. 스프레드가 통계적 임계치(예: +-2 시그마)를 이탈할 때 스프레드 매도/매수 진입.
      3. 평균 회귀(Mean Reversion) 시점에 청산하여 무위험에 가까운 현금 알파 수취.
    """
    def __init__(self, config: Dict[str, Any]):
        self.params = config.get("strategies", {}).get("strategy_3", {}).get("params", {})
        self.z_entry_threshold = self.params.get("z_score_threshold", 1.5) # Relaxed from 2.5 to 1.5 for active entries
        self.z_exit_threshold = self.params.get("z_exit_threshold", 0.2) # Relaxed from 0.0 to 0.2 for quick rotation
        
        # 내부 상태 관리
        self.active_position = None  # "SHORT_SPREAD" 또는 "LONG_SPREAD" 또는 None
        self.cooldown_ticks = 0
        logger.info("Statistical Arbitrage Strategy (Strategy 3) Initialized with 30% Capital Allocation.")

    def calculate_z_score(self, spread_series: List[float]) -> float:
        """
        주어진 스프레드 시세 리스트를 바탕으로 현재 Z-Score 산출
        """
        if not spread_series or len(spread_series) < 10:
            return 0.0
        
        arr = np.array(spread_series)
        mean = np.mean(arr)
        std = np.std(arr)
        
        if std == 0:
            return 0.0
        
        current_spread = spread_series[-1]
        z_score = (current_spread - mean) / std
        return float(z_score)

    def evaluate_arbitrage(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        [메인 통계 차익 평가 루틴]
        - 현선물 가격 데이터 및 최근 스프레드 시세를 받아 Z-Score를 분석하고 시그널 발행.
        - 매매 총 수수료 대비 현재 예상 수익을 비교하여 조기 청산하는 '수수료 방어 조건부 조기 청산' 로직 탑재.
        """
        spread_history = market_data.get("spread_history", [])
        total_fees = market_data.get("total_fees", 0.0)
        current_pnl = market_data.get("current_pnl", 0.0)
        
        z_score = self.calculate_z_score(spread_history)
        
        signals = []
        status = "HOLD"
        
        if self.cooldown_ticks > 0:
            self.cooldown_ticks -= 1

        # 1. 포지션이 없는 경우: 진입 조건 탐색
        if self.active_position is None:
            if self.cooldown_ticks == 0:
                if z_score >= self.z_entry_threshold:
                    self.active_position = "SHORT_SPREAD"
                    status = "ENTER_SHORT_SPREAD"
                    signals.append({
                        "action": "EXECUTE_STAT_ARB",
                        "type": "SHORT_SPREAD",
                        "z_score": z_score,
                        "reason": f"Z-Score ({z_score:.2f}) exceeded upper threshold (+{self.z_entry_threshold}). Selling spread."
                    })
                elif z_score <= -self.z_entry_threshold:
                    self.active_position = "LONG_SPREAD"
                    status = "ENTER_LONG_SPREAD"
                    signals.append({
                        "action": "EXECUTE_STAT_ARB",
                        "type": "LONG_SPREAD",
                        "z_score": z_score,
                        "reason": f"Z-Score ({z_score:.2f}) breached lower threshold (-{self.z_entry_threshold}). Buying spread."
                    })

        # 2. 포지션을 보유 중인 경우: 평균 회귀 및 수수료/마찰 비용 대비 조기 청산 탐색
        else:
            # 타 전략 수수료 대비 현재 차익의 실익이 1.2배 상회 시 강제 익절 조기 청산 (수수료 방어 컷오프)
            is_fee_cover_exit = (total_fees > 0 and current_pnl >= total_fees * 1.2)
            
            if self.active_position == "SHORT_SPREAD" and (z_score <= self.z_exit_threshold or is_fee_cover_exit):
                reason_str = f"Z-Score returned to mean ({z_score:.2f})." if not is_fee_cover_exit else f"Fee cover profit lock triggered (PnL: ₩{current_pnl:,.0f} >= 1.2x Fees: ₩{total_fees:,.0f})."
                signals.append({
                    "action": "CLOSE_STAT_ARB",
                    "type": "CLOSE_SHORT_SPREAD",
                    "z_score": z_score,
                    "reason": reason_str
                })
                self.active_position = None
                self.cooldown_ticks = 20 # 청산 후 20틱 쿨다운 단축 (자금 순환 가속)
                status = "CLOSED"
            elif self.active_position == "LONG_SPREAD" and (z_score >= -self.z_exit_threshold or is_fee_cover_exit):
                reason_str = f"Z-Score returned to mean ({z_score:.2f})." if not is_fee_cover_exit else f"Fee cover profit lock triggered (PnL: ₩{current_pnl:,.0f} >= 1.2x Fees: ₩{total_fees:,.0f})."
                signals.append({
                    "action": "CLOSE_STAT_ARB",
                    "type": "CLOSE_LONG_SPREAD",
                    "z_score": z_score,
                    "reason": reason_str
                })
                self.active_position = None
                self.cooldown_ticks = 20 # 청산 후 20틱 쿨다운 단축
                status = "CLOSED"

        return {
            "strategy": "Strategy_3_StatArb",
            "active": self.active_position is not None,
            "current_z_score": z_score,
            "status": status,
            "signals": signals
        }
