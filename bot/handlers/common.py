from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram import Bot

from bot.keyboards import group_select_keyboard, main_menu_keyboard
from bot.services.repository import Repository


async def upsert_user_from_message(message: Message, repo: Repository) -> dict:
    return await repo.upsert_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )


async def upsert_user_from_callback(callback: CallbackQuery, repo: Repository) -> dict:
    return await repo.upsert_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )


async def require_groups(message: Message, repo: Repository, user: dict) -> list[dict] | None:
    groups = await repo.get_user_groups(user["id"])
    if not groups:
        await message.answer(
            "У вас пока нет групп.\nНажмите «🤝 Создать группу», чтобы начать.",
            reply_markup=main_menu_keyboard(),
        )
        return None
    return groups


async def resolve_active_group(user: dict, repo: Repository) -> dict | None:
    groups = await repo.get_user_groups(user["id"])
    if not groups:
        return None

    if len(groups) == 1:
        await repo.set_active_group(user["id"], groups[0]["id"])
        return groups[0]

    active_id = user.get("active_group_id")
    if active_id:
        for group in groups:
            if group["id"] == active_id:
                return group
        await repo.set_active_group(user["id"], None)

    return None


def active_group_label(group: dict) -> str:
    return f"📌 {group['name']}"


async def ensure_active_group(
    message: Message,
    repo: Repository,
    user: dict,
    *,
    callback_prefix: str,
    prompt: str = "Выберите группу:",
) -> dict | None:
    group = await resolve_active_group(user, repo)
    if group:
        return group

    groups = await repo.get_user_groups(user["id"])
    if not groups:
        await message.answer(
            "У вас пока нет групп.",
            reply_markup=main_menu_keyboard(),
        )
        return None

    await message.answer(
        f"{prompt}\n\n"
        "Подсказка: выберите группу один раз — она запомнится. "
        "Сменить можно через «🔄 Сменить группу».",
        reply_markup=group_select_keyboard(
            groups,
            callback_prefix,
            user.get("active_group_id"),
        ),
    )
    return None


async def set_active_and_get_group(
    repo: Repository,
    user_id: int,
    group_id: int,
) -> dict | None:
    if not await repo.is_group_member(group_id, user_id):
        return None
    await repo.set_active_group(user_id, group_id)
    return await repo.get_group(group_id)


async def notify_group_members(
    bot: Bot,
    repo: Repository,
    group_id: int,
    text: str,
    *,
    exclude_user_ids: set[int] | None = None,
) -> None:
    exclude = exclude_user_ids or set()
    members = await repo.get_group_members(group_id)
    for member in members:
        if member["id"] in exclude:
            continue
        try:
            await bot.send_message(
                member["telegram_id"],
                text,
                reply_markup=main_menu_keyboard(),
            )
        except Exception:
            pass
