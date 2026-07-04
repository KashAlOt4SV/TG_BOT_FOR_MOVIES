import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import load_config
from bot.database import Database
from bot.handlers import actions, groups, media, start, watch
from bot.middlewares import MovieLookupMiddleware, RepositoryMiddleware, ResetStateOnMenuMiddleware
from bot.services.movie_lookup import MovieLookupService
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
    movie_lookup = MovieLookupService(
        kinopoisk_api_key=config.kinopoisk_api_key,
        omdb_api_key=config.omdb_api_key,
    )

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.middleware(ResetStateOnMenuMiddleware())
    dp.update.middleware(RepositoryMiddleware(repo))
    dp.update.middleware(MovieLookupMiddleware(movie_lookup))

    dp.include_router(start.router)
    dp.include_router(groups.router)
    dp.include_router(media.router)
    dp.include_router(watch.router)
    dp.include_router(actions.router)

    logger.info("Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
