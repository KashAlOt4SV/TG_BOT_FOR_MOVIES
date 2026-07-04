from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, TelegramObject

from bot.keyboards import MENU_BUTTON_TEXTS
from bot.services.repository import Repository


class ResetStateOnMenuMiddleware(BaseMiddleware):
    """Сбрасывает FSM при нажатии любой кнопки главного меню."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.text in MENU_BUTTON_TEXTS:
            state: FSMContext | None = data.get("state")
            if state and await state.get_state() is not None:
                await state.clear()
        return await handler(event, data)


class RepositoryMiddleware(BaseMiddleware):
    def __init__(self, repo: Repository):
        self.repo = repo

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["repo"] = self.repo
        return await handler(event, data)
