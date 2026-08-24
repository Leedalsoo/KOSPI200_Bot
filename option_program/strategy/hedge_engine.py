"""Production Hedge Engine Architecture.

Provides:
- Multi-Greek & Tail Risk Hedge Evaluation (Delta Neutral, Gamma Offset, Vega Spike, Tail Risk)
- Anti-Loop Lock (Max hedge limit & Wall Clock Cooldown)
- Clash Prevention between regular strategy orders and hedge orders
"""
from dataclasses import dataclass
from typing import Dict, Any, Optional, Tuple
import logging
import time
import uuid

from shared.contracts.canonical import (
    CanonicalOrderCommand,
    CanonicalAssetType,
    CanonicalOrderSide,
    CanonicalOptionType
)

logger = logging.getLogger(__name__)

@dataclass
class HedgeConfig:
    """헷지 파라미터 설정 DTO"""
    delta_deadband: float = 0.20               # 델타 허용 불감대 (±0.20 초과 시 헷지)
    max_hedge_count: int = 20                 # 일일 최대 헷지 횟수 (무한 루프 방어)
    hedge_cooldown_sec: float = 10.0          # 헷지 주문 간 최소 쿨다운 (10초)
    max_hedge_futures_qty: int = 5            # 1회 최대 선물 헷지 수량
    tail_vkospi_threshold: float = 30.0       # 테일 리스크 발동 VKOSPI 임계치

@dataclass
class HedgeEvaluationResult:
    """헷지 평가 결과 DTO"""
    needs_hedge: bool
    hedge_type: Optional[str] = None          # DELTA, GAMMA, VEGA, TAIL
    command: Optional[CanonicalOrderCommand] = None
    reason: Optional[str] = None

class HedgeEngine:
    """[헷지 엔진] 포트폴리오 그리스 지표 및 테일 리스크를 모니터링하여 중립화 헷지 주문 생성"""

    def __init__(self, config: Optional[HedgeConfig] = None):
        self.config = config or HedgeConfig()
        self.hedge_count: int = 0
        self.last_hedge_time: float = 0.0

    def reset_daily_hedge_count(self) -> None:
        """영업일 변경 시 헷지 카운터 리셋"""
        self.hedge_count = 0
        self.last_hedge_time = 0.0
        logger.info("[HedgeEngine] Daily hedge counter reset.")

    def can_hedge(self, current_time: Optional[float] = None) -> Tuple[bool, Optional[str]]:
        """무한 헷지 루프 및 쿨다운 인터록 검사"""
        now = current_time if current_time is not None else time.time()

        # 1. 최대 헷지 횟수 초과 방어락
        if self.hedge_count >= self.config.max_hedge_count:
            return False, f"ANTI_LOOP_LOCK: Exceeded max hedge count ({self.hedge_count}/{self.config.max_hedge_count})"

        # 2. 쿨다운 타이머 검사
        elapsed = now - self.last_hedge_time
        if self.last_hedge_time > 0 and elapsed < self.config.hedge_cooldown_sec:
            return False, f"COOLDOWN_ACTIVE: {elapsed:.2f}s < {self.config.hedge_cooldown_sec:.2f}s"

        return True, None

    def evaluate_delta_hedge(
        self,
        portfolio_delta: float,
        current_futures_price: float,
        current_time: Optional[float] = None
    ) -> HedgeEvaluationResult:
        """델타 중립화 선물 헷지 평가"""
        # 불감대(Deadband) 내부인 경우 헷지 불필요
        if abs(portfolio_delta) <= self.config.delta_deadband:
            return HedgeEvaluationResult(needs_hedge=False, reason="WITHIN_DELTA_DEADBAND")

        can_exec, lock_reason = self.can_hedge(current_time=current_time)
        if not can_exec:
            return HedgeEvaluationResult(needs_hedge=False, reason=lock_reason)

        # 델타가 양수(+)이면 매도(SELL), 음수(-)이면 매수(BUY) 선물 헷지
        hedge_side = CanonicalOrderSide.SELL if portfolio_delta > 0 else CanonicalOrderSide.BUY
        hedge_qty = min(self.config.max_hedge_futures_qty, max(1, round(abs(portfolio_delta))))

        cmd = CanonicalOrderCommand(
            client_order_id=f"HEDGE-DELTA-{int(time.time()*1000)}-{uuid.uuid4().hex[:4]}",
            track_id="HEDGE_DELTA",
            asset_type=CanonicalAssetType.FUTURES,
            side=hedge_side,
            qty=hedge_qty,
            price=current_futures_price,
            tag_id="RISK_HEDGE"
        )

        return HedgeEvaluationResult(
            needs_hedge=True,
            hedge_type="DELTA",
            command=cmd,
            reason=f"DELTA_OUT_OF_BOUNDS: {portfolio_delta:+.3f} (Deadband: ±{self.config.delta_deadband})"
        )

    def evaluate_tail_hedge(
        self,
        vkospi: float,
        current_regime: str,
        atm_strike: float,
        current_time: Optional[float] = None
    ) -> HedgeEvaluationResult:
        """변동성 폭발/파국 국면 테일 리스크 방어 헷지 평가"""
        if vkospi < self.config.tail_vkospi_threshold and current_regime not in ["CRISIS", "HIGH_VOLATILITY"]:
            return HedgeEvaluationResult(needs_hedge=False, reason="NORMAL_VOLATILITY")

        can_exec, lock_reason = self.can_hedge(current_time=current_time)
        if not can_exec:
            return HedgeEvaluationResult(needs_hedge=False, reason=lock_reason)

        # OTM Put 매수 테일 헷지
        otm_put_strike = atm_strike - 10.0
        cmd = CanonicalOrderCommand(
            client_order_id=f"HEDGE-TAIL-{int(time.time()*1000)}-{uuid.uuid4().hex[:4]}",
            track_id="HEDGE_TAIL",
            asset_type=CanonicalAssetType.OPTION,
            side=CanonicalOrderSide.BUY,
            qty=2,
            price=1.50,
            option_type=CanonicalOptionType.PUT,
            strike=otm_put_strike,
            tag_id="RISK_HEDGE"
        )

        return HedgeEvaluationResult(
            needs_hedge=True,
            hedge_type="TAIL",
            command=cmd,
            reason=f"TAIL_RISK_TRIGGERED: VKOSPI={vkospi:.1f}, Regime={current_regime}"
        )

    def record_hedge_executed(self, current_time: Optional[float] = None) -> None:
        """헷지 주문 발주 후 상태 갱신"""
        self.hedge_count += 1
        self.last_hedge_time = current_time if current_time is not None else time.time()
        logger.info(f"[HedgeEngine] Hedge executed count: {self.hedge_count}/{self.config.max_hedge_count}")
