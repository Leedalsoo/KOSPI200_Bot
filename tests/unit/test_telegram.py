# -*- coding: utf-8 -*-
import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from interface.controllers import ManualCommandController
from interface.telegram_bot import TelegramBotAgent



def _make_agent(allowed_chat_id: int = 12345) -> TelegramBotAgent:
    """테스트용 TelegramBotAgent 헬퍼"""
    controller = AsyncMock(spec=ManualCommandController)
    controller._is_halted = False
    return TelegramBotAgent(controller, allowed_chat_id=allowed_chat_id)


def _make_update(chat_id: int, text: str, update_id: int = 1) -> dict:  # type: ignore[type-arg]
    """테스트용 Telegram Update 딕셔너리 헬퍼"""
    return {
        "update_id": update_id,
        "message": {
            "chat": {"id": chat_id},
            "text": text,
        },
    }


@pytest.mark.asyncio
async def test_unauthorized_command_block() -> None:
    """[목표 B 검증] 비인가 ID(99999)의 명령 차단 — controller 메서드 미호출 증명"""
    bot = _make_agent(allowed_chat_id=12345)

    update = _make_update(chat_id=99999, text="/stop")
    await bot._handle_update(update)

    # 비인가 사용자 명령이므로 컨트롤러는 절대 호출되지 않아야 함
    bot.controller.trigger_panic_halt.assert_not_called()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_panic_stop_trigger() -> None:
    """[목표 C 검증] 인가된 ID의 /stop 명령 시 controller.trigger_panic_halt 호출 증명"""
    bot = _make_agent(allowed_chat_id=12345)

    update = _make_update(chat_id=12345, text="/stop")
    await bot._handle_update(update)

    # trigger_panic_halt가 정확히 1회 호출되어야 함
    bot.controller.trigger_panic_halt.assert_called_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_command_normalization_strip_lower() -> None:
    """[목표 B 방어 지령 검증] 공백/대소문자 혼용 명령도 정상 처리됨을 증명"""
    bot = _make_agent(allowed_chat_id=12345)

    # 공백과 대문자가 혼용된 명령 → strip().lower()로 정규화되어야 함
    update = _make_update(chat_id=12345, text="  /STOP  ")
    await bot._handle_update(update)

    bot.controller.trigger_panic_halt.assert_called_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_start_creates_isolated_task() -> None:
    """[목표 A 검증] start() 호출 시 메인 루프와 분리된 태스크가 생성됨을 증명"""
    bot = _make_agent()

    # _poll_messages가 즉시 종료되도록 패치
    async def _noop_poll() -> None:
        return

    with patch.object(bot, "_poll_messages", side_effect=_noop_poll):
        await bot.start()
        assert bot._poll_task is not None
        # 태스크가 별도로 존재함을 단언
        assert isinstance(bot._poll_task, asyncio.Task)
        await bot.stop()


@pytest.mark.asyncio
async def test_bot_error_isolated_from_engine() -> None:
    """[목표 A 방어 지령 검증] 봇 폴링 오류가 예외를 전파하지 않고 격리됨을 증명"""
    bot = _make_agent()

    # _fetch_updates가 예외를 던지도록 패치
    async def _raise_error() -> list:  # type: ignore[type-arg]
        raise RuntimeError("Network timeout")

    with patch.object(bot, "_fetch_updates", side_effect=_raise_error):
        # _poll_messages가 예외를 삼키고 조용히 종료해야 함
        await bot._poll_messages()  # 예외가 외부로 전파되지 않아야 함


@pytest.mark.asyncio
async def test_update_id_advances_after_processing() -> None:
    """[목표 B 검증] 처리된 업데이트의 update_id가 갱신되어 중복 처리를 방지함을 증명"""
    bot = _make_agent(allowed_chat_id=12345)

    update = _make_update(chat_id=12345, text="/status", update_id=42)
    await bot._handle_update(update)

    assert bot._last_update_id == 42
