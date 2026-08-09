# -*- coding: utf-8 -*-
"""
[Order & Hedge Invalidation Engine]
- 6대 무효화 사유 (A~F) 및 6단계 계층적 우선순위 구조 적용
- 우선순위: C (리스크) > F (시스템대조) > B (시장상태) > D (전제조건) > A (포지션) > E (시간)
- O(1) Bitmask 비트연산 평가 파이프라인
"""

import logging
from enum import IntFlag
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class InvalidationReason(IntFlag):
    NONE           = 0
    TIME_EXPIRE    = 1 << 0  # 0b000001 (E: 시간 무효화)
    POSITION_LVL   = 1 << 1  # 0b000010 (A: 포지션 레벨 무효화)
    PRECONDITION   = 1 << 2  # 0b000100 (D: 전제 조건 붕괴)
    MARKET_STATE   = 1 << 3  # 0b001000 (B: 시장 상태 무효화)
    SYS_RECON      = 1 << 4  # 0b010000 (F: 시스템 대조 미복구)
    RISK_LIMIT     = 1 << 5  # 0b100000 (C: 리스크 한도 초과 - 최우선)


class OrderInvalidationEngine:
    """
    주문 및 헤지 조건 무효화 평가 오케스트레이터
    """
    def __init__(self, max_margin_ratio: float = 92.0, max_daily_drawdown_pct: float = 15.0):
        self.max_margin_ratio = max_margin_ratio
        self.max_daily_drawdown_pct = max_daily_drawdown_pct

    def evaluate_invalidation(
        self,
        order: Dict[str, Any],
        account_state: Dict[str, Any],
        market_state: Dict[str, Any],
        position_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        6단계 우선순위 (C > F > B > D > A > E) 순차 및 Bitmask 연산 평가
        """
        flags = InvalidationReason.NONE
        reasons: List[str] = []

        # ── [C] 1순위: 리스크 레벨 무효화 (계좌 전체 리스크 최우선) ───────────
        margin_ratio = account_state.get("margin_ratio", 0.0)
        daily_loss_pct = account_state.get("daily_loss_pct", 0.0)
        risk_engine_locked = account_state.get("risk_engine_locked", False)

        if margin_ratio > self.max_margin_ratio:
            flags |= InvalidationReason.RISK_LIMIT
            reasons.append(f"C-LEVEL: Margin ratio ({margin_ratio:.1f}%) exceeded limit ({self.max_margin_ratio}%)")

        if daily_loss_pct >= self.max_daily_drawdown_pct:
            flags |= InvalidationReason.RISK_LIMIT
            reasons.append(f"C-LEVEL: Daily drawdown ({daily_loss_pct:.1f}%) hit kill-switch threshold")

        if risk_engine_locked:
            flags |= InvalidationReason.RISK_LIMIT
            reasons.append("C-LEVEL: Risk Engine emitted global trade ban (STANDBY_OVERRIDE)")

        # C단계 걸릴 경우 최우선 무조건 취소 (Cancel All Broadcast)
        if flags & InvalidationReason.RISK_LIMIT:
            return {
                "should_cancel": True,
                "priority_level": "C (RISK_LIMIT)",
                "action": "CANCEL_ALL_BROADCAST",
                "bitmask": int(flags),
                "reasons": reasons
            }

        # ── [F] 2순위: 시스템 재시작 / 재연결 대조 (Reconciliation) ─────────
        sys_reconnected = market_state.get("sys_reconnected", False)
        parent_restored = position_state.get("parent_restored", True)

        if sys_reconnected and not parent_restored:
            flags |= InvalidationReason.SYS_RECON
            reasons.append("F-LEVEL: System reconnected but parent position reconciliation failed")
            return {
                "should_cancel": True,
                "priority_level": "F (SYS_RECON)",
                "action": "CANCEL_ORPHAN_ORDER",
                "bitmask": int(flags),
                "reasons": reasons
            }

        # ── [B] 3순위: 시장 상태 레벨 무효화 (서킷브레이커/롤오버) ───────────
        circuit_breaker = market_state.get("circuit_breaker", False)
        is_expiry_rollover = market_state.get("is_expiry_rollover", False)
        iv_explosion = market_state.get("iv_explosion", False)

        if circuit_breaker:
            flags |= InvalidationReason.MARKET_STATE
            reasons.append("B-LEVEL: Circuit breaker active. Canceling order for auction reset")
        if is_expiry_rollover:
            flags |= InvalidationReason.MARKET_STATE
            reasons.append("B-LEVEL: Monthly expiry rollover. Order cannot be carried over to new contract")
        if iv_explosion:
            flags |= InvalidationReason.MARKET_STATE
            reasons.append("B-LEVEL: Extreme IV explosion (>300%). Assumptions invalidated")

        if flags & InvalidationReason.MARKET_STATE:
            return {
                "should_cancel": True,
                "priority_level": "B (MARKET_STATE)",
                "action": "CANCEL_IMMEDIATE",
                "bitmask": int(flags),
                "reasons": reasons
            }

        # ── [D] 4순위: 전제 조건 자체의 무효화 (동적 ATR 이탈) ─────────────
        entry_price = order.get("entry_price", 0.0)
        current_price = market_state.get("current_price", 0.0)
        daily_atr = market_state.get("daily_atr", 1.25)
        
        # 동적 ATR 반영 이탈 임계선: max(1.5, 1.2 * ATR)
        effective_stop_pts = max(1.5, 1.2 * daily_atr)
        price_diff = abs(current_price - entry_price)

        if entry_price > 0 and price_diff >= (effective_stop_pts * 2.0):
            flags |= InvalidationReason.PRECONDITION
            reasons.append(f"D-LEVEL: Price gap ({price_diff:.2f}pt) exceeded dynamic ATR threshold ({effective_stop_pts * 2.0:.2f}pt)")
            return {
                "should_cancel": True,
                "priority_level": "D (PRECONDITION)",
                "action": "CANCEL_AND_REEVALUATE",
                "bitmask": int(flags),
                "reasons": reasons
            }

        # ── [A] 5순위: 포지션 레벨 무효화 (원포지션 소멸/부분체결) ────────────
        parent_active = position_state.get("parent_active", True)
        signal_reversed = position_state.get("signal_reversed", False)
        partial_fill_qty = order.get("partial_fill_qty", 0)
        total_order_qty = order.get("total_order_qty", 0)

        if not parent_active:
            flags |= InvalidationReason.POSITION_LVL
            reasons.append("A-LEVEL: Parent position closed or disappeared")
            return {
                "should_cancel": True,
                "priority_level": "A (POSITION_LVL)",
                "action": "CASCADING_CANCEL",
                "bitmask": int(flags),
                "reasons": reasons
            }

        if signal_reversed:
            flags |= InvalidationReason.POSITION_LVL
            reasons.append("A-LEVEL: Signal direction reversed. Canceling pending order")
            return {
                "should_cancel": True,
                "priority_level": "A (POSITION_LVL)",
                "action": "CANCEL_AND_REVERSE",
                "bitmask": int(flags),
                "reasons": reasons
            }

        if 0 < partial_fill_qty < total_order_qty:
            recalculate_qty = partial_fill_qty
            return {
                "should_cancel": False,
                "action": "RECALCULATE_AND_REISSUE",
                "new_qty": recalculate_qty,
                "reason": f"A-LEVEL: Partial fill detected ({partial_fill_qty}/{total_order_qty}). Reissuing matched hedge"
            }

        # ── [E] 6순위: 시간 무효화 (당일 소멸 / TTD 15분) ─────────────────
        elapsed_seconds = order.get("elapsed_seconds", 0)
        is_market_closing = market_state.get("is_market_closing", False)

        if is_market_closing:
            flags |= InvalidationReason.TIME_EXPIRE
            reasons.append("E-LEVEL: Day order expired at market close (15:30)")
        if elapsed_seconds > 900:  # 15분 = 900초
            flags |= InvalidationReason.TIME_EXPIRE
            reasons.append(f"E-LEVEL: TTD timeout (Elapsed: {elapsed_seconds}s > 900s)")

        if flags & InvalidationReason.TIME_EXPIRE:
            return {
                "should_cancel": True,
                "priority_level": "E (TIME_EXPIRE)",
                "action": "CANCEL_EXPIRED",
                "bitmask": int(flags),
                "reasons": reasons
            }

        return {
            "should_cancel": False,
            "action": "KEEP_ACTIVE",
            "bitmask": 0,
            "reasons": ["ALL_CLEAR"]
        }
