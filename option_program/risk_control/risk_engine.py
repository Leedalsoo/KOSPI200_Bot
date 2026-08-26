"""Production Risk Engine, Risk Sensors & Pre-Trade Risk Gate Architecture.

Provides:
- RiskConfig: Comprehensive risk parameter thresholds (Margin, Max Qty, Daily Loss, Kill Switch).
- RiskSensor: Continuous monitoring of market volatility spikes, macro regimes, and account equity drawdowns.
- RiskEngine: Multi-layer risk admission evaluation across Strategy Track 1~9.
- RiskGate: Authoritative pre-trade gateway issuing cryptographic/unique RiskApprovalToken.
"""
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple
import uuid
import logging
import time
import math

from shared.contracts.canonical import (
    CanonicalOrderCommand,
    CanonicalAccountSummary,
    CanonicalAssetType
)
from shared.core.contracts import RiskApprovalToken, OrderStatus
from virtual_securities_firm.margin.margin_engine import MarginEngine

logger = logging.getLogger(__name__)

@dataclass
class RiskConfig:
    """리스크 한도 파라미터 설정 DTO"""
    max_order_qty: int = 50                          # 1회 최대 주문 수량
    max_daily_loss_krw: float = 10_000_000.0         # 일일 최대 누적 허용 손실 (1천만원)
    max_margin_utilization_ratio: float = 0.85       # 최대 증거금 사용률 (85%)
    max_position_per_instrument: int = 100           # 종목당 최대 보유 수량
    vol_spike_threshold_multiplier: float = 1.30     # 변동성 스파이크 배율 임계치
    margin_diet_active: bool = False                 # 긴급 마진 다이어트 활성화 여부

@dataclass
class RiskSensorSnapshot:
    """실시간 리스크 센서 관측 스냅샷 DTO"""
    is_vol_spike: bool = False
    is_crisis_regime: bool = False
    is_margin_diet_required: bool = False
    active_vol_ratio: float = 1.0
    reason: str = "NORMAL"

@dataclass
class RiskEvaluationResult:
    """리스크 심사 결과 DTO"""
    is_approved: bool
    rejection_reason: Optional[str] = None
    required_margin: float = 0.0
    estimated_margin_ratio: float = 0.0
    token: Optional[RiskApprovalToken] = None

class RiskSensor:
    """[리스크 센서] 실시간 시장 변동성, 마진 상태, 국면 위험을 지속 감시"""

    def __init__(self, config: Optional[RiskConfig] = None):
        self.config = config or RiskConfig()

    def scan_risk(
        self,
        active_vol: float,
        base_vol: float,
        current_regime: str = "NORMAL",
        account_margin_ratio: float = 0.0
    ) -> RiskSensorSnapshot:
        """시장 데이터 및 계좌 상태 기반 리스크 센싱"""
        # 1. 결측치 및 NaN 방어
        if any(v is None or (isinstance(v, float) and math.isnan(v)) for v in [active_vol, base_vol]):
            return RiskSensorSnapshot(reason="INVALID_OR_NAN_SENSOR_INPUT")

        vol_ratio = (active_vol / base_vol) if base_vol > 0 else 1.0
        is_vol_spike = vol_ratio >= self.config.vol_spike_threshold_multiplier
        is_crisis = current_regime in ["CRISIS", "HIGH_VOLATILITY", "EXTREME_MOVE"]
        is_margin_diet = account_margin_ratio > self.config.max_margin_utilization_ratio

        reason = "NORMAL"
        if is_margin_diet:
            reason = f"MARGIN_DIET_TRIGGERED (Ratio={account_margin_ratio:.2%})"
        elif is_vol_spike:
            reason = f"VOLATILITY_SPIKE_DETECTED (Ratio={vol_ratio:.2f})"
        elif is_crisis:
            reason = f"CRISIS_REGIME_ACTIVE ({current_regime})"

        return RiskSensorSnapshot(
            is_vol_spike=is_vol_spike,
            is_crisis_regime=is_crisis,
            is_margin_diet_required=is_margin_diet,
            active_vol_ratio=vol_ratio,
            reason=reason
        )

class RiskEngine:
    """[리스크 엔진] Track 1~9의 주문 명령에 대해 다층 리스크를 사전 심사"""

    def __init__(
        self,
        config: Optional[RiskConfig] = None,
        margin_engine: Optional[MarginEngine] = None,
        risk_sensor: Optional[RiskSensor] = None
    ):
        self.config = config or RiskConfig()
        self.margin_engine = margin_engine or MarginEngine()
        self.sensor = risk_sensor or RiskSensor(self.config)
        self._is_kill_switch_active: bool = False
        self._daily_realized_loss: float = 0.0

    def trigger_kill_switch(self, reason: str = "MANUAL_PANIC_STOP") -> None:
        self._is_kill_switch_active = True
        logger.critical(f"[RiskEngine] EMERGENCY KILL SWITCH TRIGGERED: {reason}")

    def reset_kill_switch(self) -> None:
        self._is_kill_switch_active = False
        logger.info("[RiskEngine] Kill Switch reset to Normal.")

    def is_kill_switch_active(self) -> bool:
        return self._is_kill_switch_active

    def record_realized_loss(self, loss_amount: float) -> None:
        if loss_amount < 0:
            self._daily_realized_loss += abs(loss_amount)

    def evaluate_order(
        self,
        command: CanonicalOrderCommand,
        account: CanonicalAccountSummary,
        positions: Optional[Dict[str, Any]] = None,
        sensor_snapshot: Optional[RiskSensorSnapshot] = None
    ) -> RiskEvaluationResult:
        """사전 거래 리스크(Pre-Trade Risk) 전수 심사"""
        positions = positions or {}

        # 1. Kill Switch 검사
        if self._is_kill_switch_active:
            return RiskEvaluationResult(
                is_approved=False,
                rejection_reason="REJECTED_BY_KILL_SWITCH"
            )

        # 2. 1회 최대 주문 수량 한도 검사
        if command.qty <= 0:
            return RiskEvaluationResult(
                is_approved=False,
                rejection_reason=f"INVALID_ORDER_QTY: {command.qty}"
            )
        if command.qty > self.config.max_order_qty:
            return RiskEvaluationResult(
                is_approved=False,
                rejection_reason=f"EXCEEDED_MAX_ORDER_QTY: {command.qty} > {self.config.max_order_qty}"
            )

        # 3. 일일 누적 손실 한도 검사
        total_loss = self._daily_realized_loss + abs(min(0.0, account.realized_pnl))
        if total_loss >= self.config.max_daily_loss_krw:
            return RiskEvaluationResult(
                is_approved=False,
                rejection_reason=f"EXCEEDED_MAX_DAILY_LOSS: {total_loss:,.0f} >= {self.config.max_daily_loss_krw:,.0f} KRW"
            )

        # 4. 종목별 포지션 한도 검사
        inst_key = f"{command.asset_type.value}_{command.strike}_{command.option_type.value if command.option_type else 'NONE'}"
        current_inst_qty = 0
        if isinstance(positions, dict):
            if inst_key in positions and isinstance(positions[inst_key], dict):
                current_inst_qty = positions[inst_key].get("qty", 0)
            elif "KOSPI200_OPTION" in positions and isinstance(positions["KOSPI200_OPTION"], dict):
                current_inst_qty = positions["KOSPI200_OPTION"].get("qty", 0)
            elif command.track_id in positions and isinstance(positions[command.track_id], dict):
                current_inst_qty = positions[command.track_id].get("qty", 0)

        if current_inst_qty + command.qty > self.config.max_position_per_instrument:
            return RiskEvaluationResult(
                is_approved=False,
                rejection_reason=f"EXCEEDED_INSTRUMENT_LIMIT: {current_inst_qty + command.qty} > {self.config.max_position_per_instrument}"
            )

        # 5. 필요 증거금 및 가용 증거금 한도 검사
        req_margin = self.margin_engine.calculate_order_margin(command)
        if account.total_balance > 0:
            est_margin_ratio = (account.used_margin + req_margin) / account.total_balance
        else:
            est_margin_ratio = 1.0

        if req_margin > account.free_margin:
            return RiskEvaluationResult(
                is_approved=False,
                rejection_reason=f"INSUFFICIENT_FREE_MARGIN: req={req_margin:,.0f} > free={account.free_margin:,.0f} KRW",
                required_margin=req_margin,
                estimated_margin_ratio=est_margin_ratio
            )

        if est_margin_ratio > self.config.max_margin_utilization_ratio:
            return RiskEvaluationResult(
                is_approved=False,
                rejection_reason=f"EXCEEDED_MAX_MARGIN_RATIO: {est_margin_ratio:.2%} > {self.config.max_margin_utilization_ratio:.2%}",
                required_margin=req_margin,
                estimated_margin_ratio=est_margin_ratio
            )

        # 6. 리스크 센서 마진 다이어트 발동 시 신규 주문 차단
        if sensor_snapshot and sensor_snapshot.is_margin_diet_required and command.tag_id != "RISK_HEDGE":
            return RiskEvaluationResult(
                is_approved=False,
                rejection_reason=f"MARGIN_DIET_ACTIVE: Blocked new entry under {sensor_snapshot.reason}",
                required_margin=req_margin,
                estimated_margin_ratio=est_margin_ratio
            )

        # 7. 모든 리스크 게이트 통과 -> 승인 토큰 발행
        order_uuid = uuid.uuid4()
        token = RiskApprovalToken(
            order_id=order_uuid,
            timestamp_ns=time.time_ns(),
            signature=f"SIG-RISK-APPROVED-{command.track_id}-{command.client_order_id}"
        )

        return RiskEvaluationResult(
            is_approved=True,
            required_margin=req_margin,
            estimated_margin_ratio=est_margin_ratio,
            token=token
        )

class RiskGate:
    """[최종 리스크 게이트] 주문 발주 직전 단일 진입점으로 작동하여 승인 토큰 부여"""

    def __init__(self, risk_engine: Optional[RiskEngine] = None):
        self.engine = risk_engine or RiskEngine()

    def admit_order(
        self,
        command: CanonicalOrderCommand,
        account: CanonicalAccountSummary,
        positions: Optional[Dict[str, Any]] = None,
        sensor_snapshot: Optional[RiskSensorSnapshot] = None
    ) -> Tuple[bool, Optional[RiskApprovalToken], Optional[str]]:
        """주문 승인/거부 판정 및 승인 토큰 반환"""
        res = self.engine.evaluate_order(command, account, positions, sensor_snapshot)
        if res.is_approved and res.token is not None:
            logger.debug(f"[RiskGate] Order {command.client_order_id} APPROVED -> Token {res.token.order_id}")
            return True, res.token, None
        else:
            logger.warning(f"[RiskGate] Order {command.client_order_id} REJECTED: {res.rejection_reason}")
            return False, None, res.rejection_reason
