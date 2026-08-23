# -*- coding: utf-8 -*-
import asyncio
import logging
from typing import Any, Dict, List
from uuid import UUID

import orjson

from shared.core.contracts import OrderStatus
from option_program.orders.oms_fsm import OmsFsm

logger = logging.getLogger(__name__)

# 데드맨 스위치 허트비트 타임아웃 (초)
_DEADMAN_TIMEOUT: float = 5.0

# 로그 출력 시 마스킹할 민감 필드 목록
_MASKED_FIELDS: frozenset[str] = frozenset({"api_key", "secret", "token", "password"})


def _mask_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """[로그 마스킹] 민감 필드를 '***'로 치환한 복사본을 반환"""
    return {k: ("***" if k in _MASKED_FIELDS else v) for k, v in data.items()}


class ManualCommandController:
    """외부 명령 및 데드맨 스위치 기반 강제 제어 컨트롤러"""

    def __init__(self, fsm: OmsFsm) -> None:
        self.fsm: OmsFsm = fsm
        self._is_halted: bool = False
        self._deadman_task: asyncio.Task[None] | None = None
        self._last_heartbeat: float = 0.0

    # -------------------------------------------------------------------------
    # [목표 B] 패닉 셧다운 — 미체결 주문 CANCELLED 강제 전이
    # -------------------------------------------------------------------------
    async def trigger_panic_halt(self, order_ids: List[UUID]) -> None:
        """[목표 B] 미체결 주문 강제 취소 및 FSM STANDBY_OVERRIDE → CANCELLED 전이"""
        if self._is_halted:
            # 🛡️ [상태 전이 충돌 방어] 이미 셧다운 중인 경우 중복 명령 무시 (Idempotency)
            logger.warning("trigger_panic_halt: system already halted — ignoring duplicate command")
            return

        self._is_halted = True
        logger.warning("PANIC HALT triggered — cancelling %d orders", len(order_ids))

        # 1단계: FSM을 STANDBY_OVERRIDE 상태로 전이하여 매매 로직 즉시 정지
        for order_id in order_ids:
            current = self.fsm.get_status(order_id)
            if current not in (OrderStatus.CANCELLED, OrderStatus.FILLED, OrderStatus.REJECTED):
                await self.fsm.transition(order_id, OrderStatus.STANDBY_OVERRIDE)

        # 2단계: STANDBY_OVERRIDE 상태에서 최종 CANCELLED로 전이
        for order_id in order_ids:
            current = self.fsm.get_status(order_id)
            if current not in (OrderStatus.CANCELLED, OrderStatus.FILLED, OrderStatus.REJECTED):
                await self.fsm.transition(order_id, OrderStatus.CANCELLED)

        logger.warning("PANIC HALT complete — all orders cancelled")

    # -------------------------------------------------------------------------
    # [목표 A] orjson 검열 파싱 및 FSM 강제 Override
    # -------------------------------------------------------------------------
    async def override_position(self, command_payload: bytes) -> None:
        """[목표 A] orjson 초고속 검열 파싱 및 FSM 강제 Override"""
        # 🛡️ [외부 명령 크래시 방어] 파싱 예외 격리 — 시스템 셧다운 차단
        try:
            data: Any = orjson.loads(command_payload)
        except orjson.JSONDecodeError as exc:
            logger.error("override_position: 400 Bad Request — invalid JSON payload: %s", exc)
            return

        if not isinstance(data, dict):
            logger.error("override_position: 400 Bad Request — payload must be a JSON object")
            return

        # 🛡️ [로그 마스킹] API Key 등 민감 필드를 치환 후 로그 출력
        safe_log = _mask_payload(data)
        logger.info("override_position: received command: %s", safe_log)

        # 필드 유효성 검증
        command = data.get("command")
        if not isinstance(command, str):
            logger.error("override_position: 400 Bad Request — missing or invalid 'command' field")
            return

        raw_ids = data.get("order_ids")
        if not isinstance(raw_ids, list):
            logger.error("override_position: 400 Bad Request — missing or invalid 'order_ids' field")
            return

        # order_ids를 UUID로 변환 (변환 실패 시 격리)
        order_ids: List[UUID] = []
        for raw_id in raw_ids:
            try:
                order_ids.append(UUID(str(raw_id)))
            except (ValueError, AttributeError) as exc:
                logger.error("override_position: invalid UUID '%s': %s", raw_id, exc)
                return

        # 명령 디스패치
        if command == "PANIC_HALT":
            await self.trigger_panic_halt(order_ids)
        elif command == "STANDBY_OVERRIDE":
            for oid in order_ids:
                await self.fsm.transition(oid, OrderStatus.STANDBY_OVERRIDE)
            logger.info("override_position: STANDBY_OVERRIDE applied to %d orders", len(order_ids))
        else:
            logger.error("override_position: 400 Bad Request — unknown command '%s'", command)

    # -------------------------------------------------------------------------
    # [목표 C] 데드맨 스위치 — 외부 오라클 Heartbeat 수신 감시
    # -------------------------------------------------------------------------
    async def receive_heartbeat(self) -> None:
        """외부 오라클로부터 생존 신호를 수신하여 타이머를 갱신"""
        self._last_heartbeat = asyncio.get_event_loop().time()
        logger.debug("Deadman switch: heartbeat received")

    async def start_deadman_switch(self, order_ids: List[UUID]) -> None:
        """[목표 C] 데드맨 스위치 워처 태스크 가동 — 타임아웃 시 PANIC HALT 자동 발동"""
        self._last_heartbeat = asyncio.get_event_loop().time()
        self._deadman_task = asyncio.create_task(
            self._deadman_watcher(order_ids)
        )
        logger.info("Deadman switch started (timeout=%.1fs)", _DEADMAN_TIMEOUT)

    async def stop_deadman_switch(self) -> None:
        """데드맨 스위치 워처 태스크 안전 정지"""
        if self._deadman_task and not self._deadman_task.done():
            self._deadman_task.cancel()
            try:
                await self._deadman_task
            except asyncio.CancelledError:
                pass

    async def _deadman_watcher(self, order_ids: List[UUID]) -> None:
        """[목표 C] 내부 워처: 5초 간격으로 Heartbeat 수신 여부를 감시"""
        try:
            while not self._is_halted:
                await asyncio.sleep(_DEADMAN_TIMEOUT)
                elapsed = asyncio.get_event_loop().time() - self._last_heartbeat
                if elapsed >= _DEADMAN_TIMEOUT:
                    logger.critical(
                        "Deadman switch: no heartbeat for %.1fs — triggering PANIC HALT", elapsed
                    )
                    await self.trigger_panic_halt(order_ids)
                    break
        except asyncio.CancelledError:
            pass
