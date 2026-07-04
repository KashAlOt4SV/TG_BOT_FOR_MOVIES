import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    database_path: Path


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise ValueError("BOT_TOKEN is not set. Copy .env.example to .env and fill in your token.")

    db_path = Path(os.getenv("DATABASE_PATH", "data/bot.db"))
    db_path.parent.mkdir(parents=True, exist_ok=True)

    return Config(bot_token=token, database_path=db_path)
