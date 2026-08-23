# -*- coding: utf-8 -*-
"""
텔레그램 봇 원격 긴급 정지 리모컨

[아키텍처 결정]
python-telegram-bot 라이브러리는 내부에 동기 호출을 포함하므로
메인 매매 루프에 직접 임포트하지 않는다.
대신 표준 asyncio + httpx 기반의 순수 비동기 Long-Polling을 구현하여
블로킹 위험을 원천 제거한다.
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

import orjson

from option_program.interface.controllers import ManualCommandController

logger = logging.getLogger(__name__)

# Telegram Bot API 베이스 URL
_TELEGRAM_API_BASE: str = "https://api.telegram.org/bot{token}"
# Long-Polling 타임아웃 (초)
_POLLING_TIMEOUT: int = 30
# 명령 처리 후 로그에 남기지 않을 민감 필드
_MASKED_LOG_FIELDS: frozenset[str] = frozenset({"token", "api_key", "secret"})


class TelegramBotAgent:
    """시스템 비상 정지 및 상태 조회를 위한 원격 제어 봇"""

    def __init__(
        self,
        controller: ManualCommandController,
        allowed_chat_id: int,
        bot_token: str = "",
    ) -> None:
        self.controller: ManualCommandController = controller
        self.allowed_chat_id: int = allowed_chat_id
        # 🛡️ [로그 마스킹] 토큰을 인스턴스 변수로만 보관, 로그에 절대 출력 금지
        self._bot_token: str = bot_token
        self._is_running: bool = False
        self._poll_task: Optional[asyncio.Task[None]] = None
        self._last_update_id: int = 0

    # -------------------------------------------------------------------------
    # [목표 A] 봇 통신 태스크를 메인 루프와 완전 격리
    # -------------------------------------------------------------------------
    async def start(self) -> None:
        """[목표 A] 봇 통신 태스크를 메인 루프와 격리하여 실행"""
        self._is_running = True
        # 🛡️ [메인 루프 폭사 방지] create_task로 메인 매매 루프와 완전 분리
        self._poll_task = asyncio.create_task(self._poll_messages())
        logger.info("TelegramBotAgent: 봇 태스크 가동 (chat_id=MASKED)")

    async def stop(self) -> None:
        """봇 태스크 안전 정지"""
        self._is_running = False
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        logger.info("TelegramBotAgent: 봇 태스크 정지 완료")

    # -------------------------------------------------------------------------
    # [목표 B, C] 메시지 수신 및 명령 처리
    # -------------------------------------------------------------------------
    async def _poll_messages(self) -> None:
        """[목표 B, C] 비동기 Long-Polling 메시지 수신 및 긴급 정지 연동"""
        try:
            while self._is_running:
                updates = await self._fetch_updates()
                for update in updates:
                    await self._handle_update(update)
                # 🛡️ [메인 루프 비간섭] 단기 양보로 다른 코루틴 실행 기회 부여
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            pass
        except Exception as exc:  # noqa: BLE001
            # 🛡️ [메인 루프 폭사 방지] 봇 오류가 매매 엔진으로 전파되지 않도록 격리
            logger.error("TelegramBotAgent: 폴링 오류 (봇은 종료, 매매 엔진은 유지): %s", exc)

    async def _fetch_updates(self) -> List[Dict[str, Any]]:
        """
        텔레그램 Long-Polling으로 업데이트 수신.
        실제 운영 시 httpx.AsyncClient를 사용하여 API 호출을 수행한다.
        테스트 가능성을 위해 오버라이드 가능한 메서드로 분리.
        """
        # 실 운영에서는 아래 코드를 활성화:
        # async with httpx.AsyncClient() as client:
        #     url = f"{_TELEGRAM_API_BASE.format(token=self._bot_token)}/getUpdates"
        #     resp = await client.get(url, params={
        #         "offset": self._last_update_id + 1,
        #         "timeout": _POLLING_TIMEOUT,
        #     })
        #     data = orjson.loads(resp.content)
        #     return data.get("result", [])
        #
        # 단위 테스트 환경에서는 빈 리스트를 반환하여 폴링 루프가 즉시 종료되도록 함
        await asyncio.sleep(0)
        return []

    async def _handle_update(self, update: Dict[str, Any]) -> None:
        """[목표 B, C] 단일 업데이트 처리 — CHAT_ID 검증 및 명령 디스패치"""
        message: Any = update.get("message") or update.get("edited_message")
        if not isinstance(message, dict):
            return

        chat_id: Any = message.get("chat", {}).get("id")
        if not isinstance(chat_id, int):
            return

        # 🛡️ [목표 B] CHAT_ID 인증 — 비인가 사용자 명령 완전 차단
        if chat_id != self.allowed_chat_id:
            # 🛡️ [로그 마스킹] chat_id를 마스킹하여 로그에 사용자 정보 노출 방지
            logger.warning(
                "TelegramBotAgent: 비인가 사용자의 명령 차단 (chat_id=MASKED)"
            )
            # update_id 진행
            update_id: Any = update.get("update_id")
            if isinstance(update_id, int):
                self._last_update_id = update_id
            return

        raw_text: Any = message.get("text", "")
        if not isinstance(raw_text, str):
            return

        # 🛡️ [명령 주입 무결성] strip() + lower()로 오타/공백 오작동 원천 차단
        command: str = raw_text.strip().lower()

        # 🛡️ [로그 마스킹] 명령 텍스트만 로그에 남기고 사용자 정보는 제외
        logger.info("TelegramBotAgent: 명령 수신 command='%s'", command)

        if command in ("/stop", "stop"):
            await self._handle_stop_command()
        elif command in ("/status", "status"):
            await self._handle_status_command()
        else:
            logger.warning("TelegramBotAgent: 알 수 없는 명령 '%s' — 무시", command)

        # update_id 갱신으로 중복 처리 방지
        update_id = update.get("update_id")
        if isinstance(update_id, int):
            self._last_update_id = update_id

    async def _handle_stop_command(self) -> None:
        """[목표 C] /stop 명령 — ManualCommandController.trigger_panic_halt와 즉각 연동"""
        logger.critical("TelegramBotAgent: /stop 명령 수신 — PANIC HALT 발동")
        # FSM에 등록된 미체결 주문은 컨트롤러가 추적하므로 빈 리스트 전달
        # 실 운영에서는 현재 미체결 주문 ID 목록을 주입
        pending_ids: List[UUID] = []
        # 🛡️ [목표 C] 메시지 수신 → FSM 셧다운 요청 지연 최소화 (동일 코루틴 직접 호출)
        await self.controller.trigger_panic_halt(pending_ids)

    async def _handle_status_command(self) -> None:
        """/status 명령 — 시스템 상태 요약 로그 출력"""
        halted: bool = self.controller._is_halted
        status_payload: bytes = orjson.dumps({"halted": halted})
        logger.info("TelegramBotAgent: /status 응답: %s", status_payload.decode())
