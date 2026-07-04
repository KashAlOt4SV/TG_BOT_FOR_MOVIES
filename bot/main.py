import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import load_config
from bot.database import Database
from bot.handlers import groups, media, start, watch
from bot.middlewares import RepositoryMiddleware
from bot.services.repository import Repository

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    config = load_config()
    db = Database(config.database_path)
    await db.init()
    repo = Repository(db)

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.middleware(RepositoryMiddleware(repo))

    dp.include_router(start.router)
    dp.include_router(groups.router)
    dp.include_router(media.router)
    dp.include_router(watch.router)

    logger.info("Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
