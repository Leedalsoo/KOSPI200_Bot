# -*- coding: utf-8 -*-
import asyncio
import logging
from datetime import datetime, time
from decimal import Decimal
from typing import List, Dict, Any, Optional

import numpy as np
import orjson

from core.base_agent import BaseAgent
from core.bus import EventBus

logger = logging.getLogger(__name__)


class ReportAgent(BaseAgent):
    """장 마감 시점 집계 보고 에이전트 (Silence is Gold 원칙)"""

    def __init__(self, bus: EventBus) -> None:
        self.bus: EventBus = bus
        self.market_close: time = time(15, 45, 0)
        self._pending_history: List[Dict[str, Any]] = []
        self._is_running: bool = False
        self._scheduler_task: Optional[asyncio.Task[None]] = None

    async def start(self) -> None:
        """[목표 A] 장 마감 트리거 스케줄러 비동기 가동"""
        self._is_running = True
        self._scheduler_task = asyncio.create_task(self._schedule_close_trigger())

    async def stop(self) -> None:
        """안전 정지 및 자원 반납"""
        self._is_running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass

    async def health_check(self) -> bool:
        return self._is_running

    async def process_message(self, message: Dict[str, Any]) -> None:
        """[목표 A] 장중에는 데이터를 큐에 쌓기만 하고, 처리는 장 마감 시에만 허용 (실시간 오염 차단)"""
        now = datetime.now().time()
        if now < self.market_close:
            # 🛡️ [실시간 오염 차단] 장 마감 전은 무조건 큐에 적재만 하고 출력 차단
            self._pending_history.append(message)
        # 장 마감 후에는 스케줄러가 직접 처리하므로 여기서는 무시

    async def _schedule_close_trigger(self) -> None:
        """[목표 A] 장 마감(15:45:00) 시점에 1회만 집계를 실행하는 비동기 스케줄러"""
        while self._is_running:
            now = datetime.now()
            close_today = datetime.combine(now.date(), self.market_close)
            seconds_until_close = (close_today - now).total_seconds()

            if seconds_until_close > 0:
                # 🛡️ [Silence is Gold] 장 마감 전까지 대기만 수행 (루프 블로킹 없음)
                await asyncio.sleep(seconds_until_close)
            
            # 장 마감 시점 도달: 단 1회 집계 후 종료
            if self._is_running:
                summary = self.generate_summary(self._pending_history)
                # 🛡️ [Silence is Gold] 실시간 중간 로그 엄금, 최종 집계 완료 시 1회만 로그 출력
                logger.info(
                    "Daily summary generated: %s",
                    orjson.dumps(summary, default=str).decode()
                )
                self._is_running = False
                break

    def generate_summary(self, history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """[목표 B, C] 엠바고 윈도우 기반 집계 및 Numpy 손익/MDD/슬리피지 연산"""
        if not history:
            return {
                "total_pnl": Decimal("0"),
                "mdd": Decimal("0"),
                "avg_slippage": Decimal("0"),
            }

        # 🛡️ [엠바고 검증] 타임스탬프 기준 데이터가 정순 정렬되어 있는지 보장
        timestamps = [
            r["timestamp"] for r in history if "timestamp" in r
        ]
        if len(timestamps) > 1:
            assert all(
                timestamps[i] <= timestamps[i + 1] for i in range(len(timestamps) - 1)
            ), "Embargo violation: history must be sorted chronologically (no look-ahead bias)"

        # 🛡️ [목표 B] 보고 시점 기준 미래 데이터 참조 방어 - 현재 시각 이후 타임스탬프 슬라이싱
        now = datetime.now()
        valid_history = [
            r for r in history
            if "timestamp" not in r or r["timestamp"] <= now
        ]

        # PnL 집계
        pnl_list = [r.get("pnl", Decimal("0")) for r in valid_history]
        slippage_list = [r.get("slippage", Decimal("0")) for r in valid_history]

        # 🛡️ [MDD 연산 무결성] 100배 스케일링 + int 변환으로 부동소수점 오차 소거
        pnl_scaled = np.array([int(Decimal(str(p)) * 100) for p in pnl_list], dtype=np.int64)
        slippage_scaled = np.array([int(Decimal(str(s)) * 100) for s in slippage_list], dtype=np.int64)

        # 누적 손익 (Cumulative PnL)
        total_pnl_scaled = int(np.sum(pnl_scaled))
        total_pnl = Decimal(str(total_pnl_scaled)) / Decimal("100")

        # MDD 계산: cummax 대비 최대 낙폭
        cumulative = np.cumsum(pnl_scaled)
        running_max = np.maximum.accumulate(cumulative)
        drawdowns = running_max - cumulative
        mdd_scaled = int(np.max(drawdowns)) if len(drawdowns) > 0 else 0
        mdd = Decimal(str(mdd_scaled)) / Decimal("100")

        # 평균 슬리피지
        avg_slippage_scaled = float(np.mean(slippage_scaled)) if len(slippage_scaled) > 0 else 0.0
        avg_slippage = Decimal(str(round(avg_slippage_scaled, 2))) / Decimal("100")

        return {
            "total_pnl": total_pnl,
            "mdd": mdd,
            "avg_slippage": avg_slippage,
        }
