from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.services.repository import Repository


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
