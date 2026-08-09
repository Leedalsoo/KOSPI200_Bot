# -*- coding: utf-8 -*-
"""
exchange/execution_ladder.py

[Phase 3] 전략별 지정가 청산 Execution Ladder

핵심 역할:
  만기 시간(DTE) 또는 현재 시각 기준으로 지정가 청산을 단계적으로 재가격합니다.
  
  청산 단계:
    Stage 1 (T-30분 이상): 일반 지정가 (목표가)
    Stage 2 (T-10분):      호가 2틱 안쪽 공격적 지정가
    Stage 3 (T-3분):       Marketable Limit (Bid/Ask에 바로 붙임)
    Stage 4 (T-1분):       Emergency Market (강제 체결)
    
  Track별 청산 정책:
    Track1:  프리미엄 50~70% 감소 시 TP / IV폭발·Strike접근 시 즉시 청산
    Track2:  평균회귀 목표가 지정가 → Z-score 실패 시 Stop
    Track3:  양 다리(Leg A/B) 동시 관리 → 한쪽 미체결 시 즉시 Cancel/Flatten
    Track4:  Delta Threshold 기반 선물 헷지 → Gamma 트레이드 언와인드
    Track5:  Gap 회귀 목표가 지정가 → VWAP 회복 실패 시 Stop
    Track6:  +50% → +100% → +200% 분할 청산 (Tail Runner 25% 유지)
    Track7:  +75% → +150% → +300% 분할 청산 (만기/Time Exit 25% 유지)
    Track8:  DTE 15일→7일→3일 계단식 청산
"""

from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from enum import Enum

from core.contracts import (
    LimitOrderRecord,
    LimitOrderType,
    OrderStatus,
    PositionExitStatus,
    PositionRecord,
)
from exchange.orderbook_sim import VirtualOrderBook

logger = logging.getLogger(__name__)

# ── 청산 단계 정의 ────────────────────────────────────────────────────────
class ExitStage(str, Enum):
    NORMAL       = "NORMAL"        # T-30분 이상: 목표가 지정가
    AGGRESSIVE   = "AGGRESSIVE"    # T-10분: 2틱 안쪽 공격
    MARKETABLE   = "MARKETABLE"    # T-3분:  Bid/Ask에 붙임
    EMERGENCY    = "EMERGENCY"     # T-1분:  강제 시장가


# ── Track별 분할 청산 정책 ───────────────────────────────────────────────
# (수익률 임계값, 해당 구간에서 청산할 비율)
TRACK6_TP_LADDER: List[Tuple[float, float]] = [
    (0.50, 0.25),   # +50%  시 25%
    (1.00, 0.25),   # +100% 시 25%
    (2.00, 0.25),   # +200% 시 25%
    # 나머지 25%: Tail Runner (만기/Time Exit)
]

TRACK7_TP_LADDER: List[Tuple[float, float]] = [
    (0.75, 0.25),   # +75%  시 25%
    (1.50, 0.25),   # +150% 시 25%
    (3.00, 0.25),   # +300% 시 25%
    # 나머지 25%: 만기/Time Exit
]

# Track8: DTE 기반 계단식 청산 (DTE 이하가 되면 해당 비율 청산)
TRACK8_DTE_LADDER: List[Tuple[float, float]] = [
    (15.0, 0.25),   # DTE <= 15: 25% 청산
    (7.0,  0.25),   # DTE <= 7:  추가 25%
    (3.0,  1.00),   # DTE <= 3:  잔여 전량 강제 청산
]

# Track1: 프리미엄 수취 목표 청산 임계 (SELL 옵션 기준 수익 비율)
TRACK1_TP_THRESHOLD = 0.60   # 프리미엄의 60% 감소 시 청산 (진입가 대비 40%만 남으면)

# 만기 긴급 청산 (DTE <= 이 값이면 무조건 청산 준비)
DTE_EMERGENCY_THRESHOLD = 3.0


@dataclass
class LadderContext:
    """
    Execution Ladder 실행 컨텍스트
    각 포지션별로 생성되어 현재 청산 단계와 진행 이력을 추적합니다.
    """
    position: PositionRecord
    target_price: Decimal              # 목표 청산가
    current_stage: ExitStage = ExitStage.NORMAL
    stage_history: List[str] = field(default_factory=list)
    tp_ladder_idx: int = 0             # 분할 청산 현재 단계 인덱스
    partial_exit_count: int = 0        # 분할 청산 완료 횟수
    created_at: datetime = field(default_factory=datetime.now)

    def advance_stage(self, new_stage: ExitStage) -> None:
        """단계 전진 및 이력 기록"""
        if new_stage != self.current_stage:
            logger.info(
                "[ExecutionLadder] %s | 청산 단계 전진: %s → %s | 목표가: %s",
                self.position.strategy_id,
                self.current_stage.value,
                new_stage.value,
                self.target_price,
            )
            self.stage_history.append(
                f"{datetime.now().strftime('%H:%M:%S')} {self.current_stage.value}→{new_stage.value}"
            )
            self.current_stage = new_stage


class ExecutionLadder:
    """
    [Phase 3] 시간 기반 지정가 재가격 엔진

    각 포지션의 청산 단계를 현재 시각과 DTE를 기반으로
    자동으로 진전시키고 재가격합니다.
    """

    # 청산 단계 전환 타임라인 (장 마감 기준 분 단위)
    STAGE_THRESHOLDS_MINUTES: Dict[ExitStage, float] = {
        ExitStage.NORMAL:     30.0,   # 30분 이상: 보통 지정가
        ExitStage.AGGRESSIVE: 10.0,   # 10분 이하: 공격적 지정가
        ExitStage.MARKETABLE: 3.0,    # 3분 이하: Marketable Limit
        ExitStage.EMERGENCY:  1.0,    # 1분 이하: 긴급 시장가
    }

    def __init__(self, orderbook: VirtualOrderBook) -> None:
        self.orderbook = orderbook
        # position_id → LadderContext 매핑
        self._contexts: Dict[str, LadderContext] = {}

    # ── 컨텍스트 관리 ────────────────────────────────────────────────────

    def register(
        self,
        position: PositionRecord,
        target_price: Decimal,
    ) -> LadderContext:
        """포지션 청산 등록"""
        ctx = LadderContext(position=position, target_price=target_price)
        self._contexts[position.position_id] = ctx
        logger.info(
            "[ExecutionLadder] 청산 등록: %s | 전략: %s | 목표가: %s | 수량: %d",
            position.position_id[:8],
            position.strategy_id,
            target_price,
            position.remaining_qty,
        )
        return ctx

    def deregister(self, position_id: str) -> None:
        """포지션 청산 완료 후 컨텍스트 제거"""
        self._contexts.pop(position_id, None)

    def get_context(self, position_id: str) -> Optional[LadderContext]:
        return self._contexts.get(position_id)

    # ── 핵심: 현재 단계 결정 ────────────────────────────────────────────

    def determine_stage(
        self,
        current_time: datetime,
        market_close: datetime,
        dte: float,
    ) -> ExitStage:
        """
        현재 시각과 DTE를 기반으로 청산 단계 결정
        
        Args:
            current_time:  현재 시뮬레이션 시각
            market_close:  당일 장 마감 시각 (15:20 KRX)
            dte:           잔여 만기 영업일 수
        """
        # DTE <= 3이면 무조건 긴급 단계
        if dte <= DTE_EMERGENCY_THRESHOLD:
            return ExitStage.EMERGENCY

        # 장 마감까지 남은 시간 (분)
        mins_to_close = (market_close - current_time).total_seconds() / 60.0

        if mins_to_close <= self.STAGE_THRESHOLDS_MINUTES[ExitStage.EMERGENCY]:
            return ExitStage.EMERGENCY
        elif mins_to_close <= self.STAGE_THRESHOLDS_MINUTES[ExitStage.MARKETABLE]:
            return ExitStage.MARKETABLE
        elif mins_to_close <= self.STAGE_THRESHOLDS_MINUTES[ExitStage.AGGRESSIVE]:
            return ExitStage.AGGRESSIVE
        else:
            return ExitStage.NORMAL

    # ── 재가격 필요 여부 ────────────────────────────────────────────────

    def should_reprice(
        self,
        ctx: LadderContext,
        current_time: datetime,
        market_close: datetime,
        dte: float,
    ) -> bool:
        """현재 단계에서 재가격이 필요한지 확인"""
        new_stage = self.determine_stage(current_time, market_close, dte)
        return new_stage != ctx.current_stage

    # ── 지정가 주문 생성 ────────────────────────────────────────────────

    def build_limit_order(
        self,
        ctx: LadderContext,
        current_time: datetime,
        market_close: datetime,
        dte: float,
        bid: Decimal,
        ask: Decimal,
        current_price: Decimal,
        qty_override: Optional[int] = None,
    ) -> LimitOrderRecord:
        """
        현재 단계에 맞는 지정가 주문 생성
        
        Args:
            ctx:           LadderContext
            current_time:  현재 시각
            market_close:  장 마감 시각
            dte:           잔여 만기
            bid/ask:       현재 호가
            current_price: 현재 기초자산 가격
            qty_override:  분할 청산 수량 (None이면 remaining_qty 전량)
        """
        pos = ctx.position
        stage = self.determine_stage(current_time, market_close, dte)
        ctx.advance_stage(stage)

        # 청산 방향: BUY 포지션이면 SELL로 청산, SELL이면 BUY로 청산
        close_side = "BUY" if pos.side == "SELL" else "SELL"

        # 단계별 지정가 결정
        asset_type = "FUTURES" if pos.option_type == "FUTURES" else "OPTIONS"
        target = ctx.target_price

        if stage == ExitStage.NORMAL:
            limit_price = self.orderbook.calc_limit_price(
                close_side, target, bid, ask, asset_type, tick_offset=0
            )
            order_type = LimitOrderType.TP.value
        elif stage == ExitStage.AGGRESSIVE:
            limit_price = self.orderbook.calc_limit_price(
                close_side, target, bid, ask, asset_type, tick_offset=2
            )
            order_type = LimitOrderType.TP.value
        elif stage == ExitStage.MARKETABLE:
            # Marketable Limit: Bid/Ask에 바로 붙임
            limit_price = bid if close_side == "SELL" else ask
            order_type = LimitOrderType.TIME_EXIT.value
        else:  # EMERGENCY
            # 긴급: 시장에서 즉시 체결 가능한 가격 (worst case)
            tick = self.orderbook.get_tick_size(current_price, asset_type)
            if close_side == "SELL":
                limit_price = bid - tick  # bid 한 틱 아래 (확실한 체결)
            else:
                limit_price = ask + tick  # ask 한 틱 위
            order_type = LimitOrderType.EMERGENCY.value

        # 최소가 보정
        if asset_type == "OPTIONS":
            limit_price = max(limit_price, Decimal("0.01"))

        qty = qty_override if qty_override is not None else pos.remaining_qty
        ctx.partial_exit_count += 1

        return LimitOrderRecord(
            order_id=f"LADDER-{pos.position_id[:8]}-{ctx.partial_exit_count}",
            position_id=pos.position_id,
            strategy_id=pos.strategy_id,
            side=close_side,
            price=limit_price,
            qty=qty,
            order_type=order_type,
            status=OrderStatus.PENDING.value,
            created_at_ns=time.time_ns(),
            reprice_count=ctx.partial_exit_count - 1,
            last_reprice_at_ns=time.time_ns(),
        )

    # ── Track별 분할 청산 신호 생성 ─────────────────────────────────────

    def check_tp_ladder_signal(
        self,
        position: PositionRecord,
        current_option_price: Decimal,
        strategy_id: str,
    ) -> Optional[Tuple[Decimal, int]]:
        """
        Track6/7 분할 TP 신호 확인
        
        Returns:
            (target_price, qty_to_close) 또는 None (청산 불요)
        """
        ctx = self._contexts.get(position.position_id)
        if ctx is None:
            return None

        entry_price = position.entry_price
        if entry_price <= Decimal("0"):
            return None

        # 수익률 계산 (BUY 포지션 기준)
        if position.side == "BUY":
            profit_ratio = float((current_option_price - entry_price) / entry_price)
        else:
            # SELL 포지션: 프리미엄 감소율
            profit_ratio = float((entry_price - current_option_price) / entry_price)

        # 전략별 Ladder 선택
        if "Track6" in strategy_id or "Track 6" in strategy_id:
            ladder = TRACK6_TP_LADDER
        elif "Track7" in strategy_id or "Track 7" in strategy_id:
            ladder = TRACK7_TP_LADDER
        else:
            return None

        # 현재 단계 이상의 임계값 도달 확인
        if ctx.tp_ladder_idx >= len(ladder):
            return None  # 모든 분할 청산 완료

        threshold, ratio = ladder[ctx.tp_ladder_idx]
        if profit_ratio >= threshold:
            close_qty = max(1, int(position.qty * ratio))
            ctx.tp_ladder_idx += 1
            logger.info(
                "[ExecutionLadder] %s | TP Ladder 단계 %d 달성! 수익률: +%.1f%% | 청산 수량: %d",
                strategy_id,
                ctx.tp_ladder_idx,
                profit_ratio * 100,
                close_qty,
            )
            return current_option_price, close_qty

        return None

    def check_dte_ladder_signal(
        self,
        position: PositionRecord,
        dte: float,
    ) -> Optional[Tuple[Decimal, int]]:
        """
        Track8 DTE 기반 계단식 청산 신호 확인
        
        Returns:
            (target_price, qty_to_close) 또는 None
        """
        ctx = self._contexts.get(position.position_id)
        if ctx is None:
            return None

        if ctx.tp_ladder_idx >= len(TRACK8_DTE_LADDER):
            return None

        dte_threshold, ratio = TRACK8_DTE_LADDER[ctx.tp_ladder_idx]
        if dte <= dte_threshold:
            close_qty = max(1, int(position.remaining_qty * ratio))
            ctx.tp_ladder_idx += 1
            logger.info(
                "[ExecutionLadder] Track8 | DTE %.1f ≤ %.1f 도달! 청산 비율: %.0f%% | 수량: %d",
                dte,
                dte_threshold,
                ratio * 100,
                close_qty,
            )
            return ctx.target_price, close_qty

        return None

    # ── 통계 ─────────────────────────────────────────────────────────────

    def get_active_count(self) -> int:
        return len(self._contexts)

    def get_summary(self) -> List[Dict]:
        result = []
        for pid, ctx in self._contexts.items():
            result.append({
                "position_id": pid[:8],
                "strategy_id": ctx.position.strategy_id,
                "stage": ctx.current_stage.value,
                "target_price": float(ctx.target_price),
                "tp_ladder_idx": ctx.tp_ladder_idx,
                "partial_count": ctx.partial_exit_count,
            })
        return result
