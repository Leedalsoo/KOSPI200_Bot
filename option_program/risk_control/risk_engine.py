"""Production Risk Engine, Risk Sensors & Pre-Trade Risk Gate Architecture.

Provides:
- RiskConfig: Comprehensive risk parameter thresholds (Margin, Max Qty, Daily Loss, Kill Switch).
- RiskSensor: Continuous monitoring of market volatility spikes, macro regimes, and account equity drawdowns.
- RiskEngine: Multi-layer risk admission evaluation across Strategy Track 1~9.
- RiskGate: Authoritative pre-trade gateway issuing cryptographic/unique RiskApprovalToken.
"""
import dataclasses
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
    account_stale_timeout_sec: float = 30.0          # 계좌 상태 Freshness 타임아웃 (30초)
    position_stale_timeout_sec: float = 30.0         # 포지션 상태 Freshness 타임아웃 (30초)

@dataclass
class RiskSensorSnapshot:
    """실시간 리스크 센서 관측 스냅샷 DTO"""
    is_vol_spike: bool = False
    is_crisis_regime: bool = False
    is_margin_diet_required: bool = False
    is_account_stale: bool = False
    is_position_stale: bool = False
    active_vol_ratio: float = 1.0
    reason: str = "NORMAL"

@dataclass
class RiskEvaluationResult:
    """리스크 심사 결과 DTO"""
    is_approved: bool
    decision: str = "ALLOW"  # "ALLOW", "REDUCE", "DENY"
    original_qty: int = 0
    approved_qty: int = 0
    rejection_reason: Optional[str] = None
    required_margin: float = 0.0
    estimated_margin_ratio: float = 0.0
    token: Optional[RiskApprovalToken] = None
    reduced_command: Optional[CanonicalOrderCommand] = None

class RiskSensor:
    """[리스크 센서] 실시간 시장 변동성, 마진 상태, 국면 위험을 지속 감시"""

    def __init__(self, config: Optional[RiskConfig] = None):
        self.config = config or RiskConfig()

    def scan_risk(
        self,
        active_vol: float,
        base_vol: float,
        current_regime: str = "NORMAL",
        account_margin_ratio: float = 0.0,
        is_account_stale: bool = False,
        is_position_stale: bool = False
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
        elif is_account_stale or is_position_stale:
            reason = f"STALE_STATE_DETECTED (AccountStale={is_account_stale}, PosStale={is_position_stale})"

        return RiskSensorSnapshot(
            is_vol_spike=is_vol_spike,
            is_crisis_regime=is_crisis,
            is_margin_diet_required=is_margin_diet,
            is_account_stale=is_account_stale,
            is_position_stale=is_position_stale,
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

    def calculate_expected_position(
        self,
        command: CanonicalOrderCommand,
        positions: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """주문 체결 시 예상되는 Instrument Position (Side & Qty) 계산"""
        positions = positions or {}
        if hasattr(command, "get_instrument_key"):
            inst_key = command.get_instrument_key()
        else:
            inst_key = f"{command.asset_type.value}_{command.strike}_{command.option_type.value if command.option_type else 'NONE'}"

        current_pos = {}
        if isinstance(positions, dict):
            if inst_key in positions and isinstance(positions[inst_key], dict):
                current_pos = positions[inst_key]
            elif "KOSPI200_OPTION" in positions and isinstance(positions["KOSPI200_OPTION"], dict) and len(positions) == 1:
                current_pos = positions["KOSPI200_OPTION"]

        curr_qty = current_pos.get("qty", 0)
        curr_side = current_pos.get("side")
        order_side = command.side.value if hasattr(command.side, "value") else str(command.side)

        if curr_qty == 0 or not curr_side:
            return {"instrument_key": inst_key, "side": order_side, "qty": command.qty}

        if curr_side == order_side:
            # 동일 방향 추가 진입
            return {"instrument_key": inst_key, "side": curr_side, "qty": curr_qty + command.qty}
        else:
            # 반대 방향 청산 / 반전
            if command.qty < curr_qty:
                # 부분 청산
                return {"instrument_key": inst_key, "side": curr_side, "qty": curr_qty - command.qty}
            elif command.qty == curr_qty:
                # 완전 청산 (FLAT)
                return {"instrument_key": inst_key, "side": "FLAT", "qty": 0}
            else:
                # 반전 (Reversal)
                return {"instrument_key": inst_key, "side": order_side, "qty": command.qty - curr_qty}

    def evaluate_order(
        self,
        command: CanonicalOrderCommand,
        account: CanonicalAccountSummary,
        positions: Optional[Dict[str, Any]] = None,
        sensor_snapshot: Optional[RiskSensorSnapshot] = None,
        allow_reduction: bool = False
    ) -> RiskEvaluationResult:
        """사전 거래 리스크(Pre-Trade Risk) 전수 심사"""
        positions = positions or {}
        original_qty = command.qty

        # 1. Kill Switch 검사
        if self._is_kill_switch_active:
            return RiskEvaluationResult(
                is_approved=False,
                decision="DENY",
                original_qty=original_qty,
                approved_qty=0,
                rejection_reason="REJECTED_BY_KILL_SWITCH"
            )

        # 2. 1회 최대 주문 수량 한도 검사
        if command.qty <= 0:
            return RiskEvaluationResult(
                is_approved=False,
                decision="DENY",
                original_qty=original_qty,
                approved_qty=0,
                rejection_reason=f"INVALID_ORDER_QTY: {command.qty}"
            )
        if command.qty > self.config.max_order_qty:
            return RiskEvaluationResult(
                is_approved=False,
                decision="DENY",
                original_qty=original_qty,
                approved_qty=0,
                rejection_reason=f"EXCEEDED_MAX_ORDER_QTY: {command.qty} > {self.config.max_order_qty}"
            )

        # 3. 일일 누적 손실 한도 검사
        total_loss = self._daily_realized_loss + abs(min(0.0, account.realized_pnl))
        if total_loss >= self.config.max_daily_loss_krw:
            return RiskEvaluationResult(
                is_approved=False,
                decision="DENY",
                original_qty=original_qty,
                approved_qty=0,
                rejection_reason=f"EXCEEDED_MAX_DAILY_LOSS: {total_loss:,.0f} >= {self.config.max_daily_loss_krw:,.0f} KRW"
            )

        # 4. 종목별 포지션 한도 검사 및 Capacity 축소(REDUCE) 처리
        effective_cmd = command
        expected_pos = self.calculate_expected_position(effective_cmd, positions)
        if expected_pos["qty"] > self.config.max_position_per_instrument:
            inst_key = expected_pos.get("instrument_key", "")
            curr_pos_qty = 0
            if inst_key in positions and isinstance(positions[inst_key], dict):
                curr_pos_qty = positions[inst_key].get("qty", 0)
            elif "KOSPI200_OPTION" in positions and isinstance(positions["KOSPI200_OPTION"], dict):
                curr_pos_qty = positions["KOSPI200_OPTION"].get("qty", 0)

            remaining_capacity = self.config.max_position_per_instrument - curr_pos_qty
            if allow_reduction and 0 < remaining_capacity < effective_cmd.qty:
                effective_cmd = dataclasses.replace(effective_cmd, qty=remaining_capacity)
            else:
                return RiskEvaluationResult(
                    is_approved=False,
                    decision="DENY",
                    original_qty=original_qty,
                    approved_qty=0,
                    rejection_reason=f"EXCEEDED_INSTRUMENT_LIMIT: {expected_pos['qty']} > {self.config.max_position_per_instrument}"
                )

        # 5. 필요 증거금 및 가용 증거금 한도 검사 및 Margin-based 축소(REDUCE) 처리
        req_margin = self.margin_engine.calculate_order_margin(effective_cmd)
        if account.total_balance > 0:
            est_margin_ratio = (account.used_margin + req_margin) / account.total_balance
        else:
            est_margin_ratio = 1.0

        if req_margin > account.free_margin:
            unit_margin = req_margin / effective_cmd.qty if effective_cmd.qty > 0 else 0.0
            max_affordable_qty = int(account.free_margin / unit_margin) if unit_margin > 0 else 0
            if allow_reduction and 0 < max_affordable_qty < effective_cmd.qty:
                effective_cmd = dataclasses.replace(effective_cmd, qty=max_affordable_qty)
                req_margin = self.margin_engine.calculate_order_margin(effective_cmd)
                if account.total_balance > 0:
                    est_margin_ratio = (account.used_margin + req_margin) / account.total_balance
            else:
                return RiskEvaluationResult(
                    is_approved=False,
                    decision="DENY",
                    original_qty=original_qty,
                    approved_qty=0,
                    rejection_reason=f"INSUFFICIENT_FREE_MARGIN: req={req_margin:,.0f} > free={account.free_margin:,.0f} KRW",
                    required_margin=req_margin,
                    estimated_margin_ratio=est_margin_ratio
                )

        if est_margin_ratio > self.config.max_margin_utilization_ratio:
            return RiskEvaluationResult(
                is_approved=False,
                decision="DENY",
                original_qty=original_qty,
                approved_qty=0,
                rejection_reason=f"EXCEEDED_MAX_MARGIN_RATIO: {est_margin_ratio:.2%} > {self.config.max_margin_utilization_ratio:.2%}",
                required_margin=req_margin,
                estimated_margin_ratio=est_margin_ratio
            )

        # 6. 리스크 센서 마진 다이어트 발동 시 신규 주문 차단
        if sensor_snapshot and sensor_snapshot.is_margin_diet_required and effective_cmd.tag_id != "RISK_HEDGE":
            return RiskEvaluationResult(
                is_approved=False,
                decision="DENY",
                original_qty=original_qty,
                approved_qty=0,
                rejection_reason=f"MARGIN_DIET_ACTIVE: Blocked new entry under {sensor_snapshot.reason}",
                required_margin=req_margin,
                estimated_margin_ratio=est_margin_ratio
            )

        # 7. 모든 리스크 게이트 통과 -> 승인 토큰 발행 (ALLOW / REDUCE 결정)
        is_reduced = (effective_cmd.qty < original_qty)
        decision_str = "REDUCE" if is_reduced else "ALLOW"

        order_uuid = uuid.uuid4()
        token = RiskApprovalToken(
            order_id=order_uuid,
            timestamp_ns=time.time_ns(),
            signature=f"SIG-RISK-APPROVED-{effective_cmd.track_id}-{effective_cmd.client_order_id}"
        )

        return RiskEvaluationResult(
            is_approved=True,
            decision=decision_str,
            original_qty=original_qty,
            approved_qty=effective_cmd.qty,
            required_margin=req_margin,
            estimated_margin_ratio=est_margin_ratio,
            token=token,
            reduced_command=effective_cmd if is_reduced else None
        )

class RiskGate:
    """[최종 리스크 게이트] 주문 발주 직전 단일 진입점으로 작동하여 승인 토큰 부여"""

    def __init__(self, risk_engine: Optional[RiskEngine] = None):
        self.engine = risk_engine or RiskEngine()
        self.last_evaluation_result: Optional[RiskEvaluationResult] = None

    def admit_order(
        self,
        command: CanonicalOrderCommand,
        account: CanonicalAccountSummary,
        positions: Optional[Dict[str, Any]] = None,
        sensor_snapshot: Optional[RiskSensorSnapshot] = None,
        allow_reduction: bool = False
    ) -> Tuple[bool, Optional[RiskApprovalToken], Optional[str]]:
        """주문 승인/거부/축소 판정 및 승인 토큰 반환"""
        res = self.engine.evaluate_order(command, account, positions, sensor_snapshot, allow_reduction=allow_reduction)
        self.last_evaluation_result = res
        if res.is_approved and res.token is not None:
            if res.decision == "REDUCE":
                logger.info(f"[RiskGate] Order {command.client_order_id} REDUCED: {res.original_qty} -> {res.approved_qty} Qty")
            logger.debug(f"[RiskGate] Order {command.client_order_id} APPROVED ({res.decision}) -> Token {res.token.order_id}")
            return True, res.token, None
        else:
            logger.warning(f"[RiskGate] Order {command.client_order_id} REJECTED: {res.rejection_reason}")
            return False, None, res.rejection_reason
