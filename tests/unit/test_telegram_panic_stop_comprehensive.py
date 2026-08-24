"""Unit Test: Telegram Bot Agent & Panic Stop Comprehensive Verification."""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from interface.controllers import ManualCommandController
from interface.telegram_bot import TelegramBotAgent

def make_test_bot(allowed_chat_id: int = 12345) -> TelegramBotAgent:
    controller = AsyncMock(spec=ManualCommandController)
    controller._is_halted = False
    return TelegramBotAgent(controller, allowed_chat_id=allowed_chat_id)

def make_test_update(chat_id: int, text: str, update_id: int = 100) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "chat": {"id": chat_id},
            "text": text,
        },
    }

@pytest.mark.asyncio
async def test_telegram_unauthorized_chat_drop():
    """Validates that commands from unauthorized chat_id are silently dropped without invoking controller."""
    bot = make_test_bot(allowed_chat_id=12345)
    unauth_update = make_test_update(chat_id=99999, text="/stop")

    await bot._handle_update(unauth_update)
    bot.controller.trigger_panic_halt.assert_not_called()

@pytest.mark.asyncio
async def test_telegram_panic_stop_triggers_controller_halt():
    """Validates that /stop command from authorized user triggers panic halt."""
    bot = make_test_bot(allowed_chat_id=12345)
    auth_update = make_test_update(chat_id=12345, text="/stop")

    await bot._handle_update(auth_update)
    bot.controller.trigger_panic_halt.assert_called_once()

@pytest.mark.asyncio
async def test_telegram_whitespace_case_insensitivity():
    """Validates command normalization across whitespaces and uppercase."""
    bot = make_test_bot(allowed_chat_id=12345)
    raw_update = make_test_update(chat_id=12345, text="   /sToP   \n")

    await bot._handle_update(raw_update)
    bot.controller.trigger_panic_halt.assert_called_once()

@pytest.mark.asyncio
async def test_telegram_background_task_exception_isolation():
    """Validates that telegram network exceptions do not propagate to engine."""
    bot = make_test_bot()

    async def _failing_fetch():
        raise ConnectionResetError("Telegram API unreachable")

    with patch.object(bot, "_fetch_updates", side_effect=_failing_fetch):
        # Should gracefully catch error without raising
        await bot._poll_messages()
