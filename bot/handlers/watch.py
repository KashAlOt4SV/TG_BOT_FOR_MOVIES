from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot.keyboards import group_select_keyboard, main_menu_keyboard
from bot.services.repository import Repository

router = Router()


async def _get_user_groups(message: Message, repo: Repository):
    return await repo.upsert_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )


@router.message(F.text == "🎬 Что посмотреть сегодня")
async def pick_random(message: Message, repo: Repository) -> None:
    user = await _get_user_groups(message, repo)
    groups = await repo.get_user_groups(user["id"])

    if not groups:
        await message.answer(
            "Сначала создайте или присоединитесь к группе.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if len(groups) == 1:
        await _do_pick_random(message, repo, groups[0]["id"])
        return

    await message.answer(
        "Выберите группу:",
        reply_markup=group_select_keyboard(groups, "pick"),
    )


@router.callback_query(F.data.startswith("pick:"))
async def pick_random_for_group(callback: CallbackQuery, repo: Repository) -> None:
    group_id = int(callback.data.split(":")[1])
    user = await repo.get_user_by_telegram_id(callback.from_user.id)

    if not user or not await repo.is_group_member(group_id, user["id"]):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    await _do_pick_random(callback.message, repo, group_id, edit=True)
    await callback.answer()


async def _do_pick_random(
    message: Message,
    repo: Repository,
    group_id: int,
    edit: bool = False,
) -> None:
    group = await repo.get_group(group_id)
    result = await repo.pick_random_watch_item(group_id)

    if result is None:
        text = (
            f"<b>{group['name']}</b>\n\n"
            "📭 Список на просмотр пуст.\n"
            "Добавьте фильмы через «➕ Предложить фильм»."
        )
    elif result["action"] == "already_watching":
        item = result["item"]
        text = (
            f"<b>{group['name']}</b>\n\n"
            f"📺 Уже выбрано для просмотра:\n<b>{item['title']}</b>\n\n"
            "Отметьте просмотренным, когда досмотрите."
        )
    else:
        item = result["item"]
        text = (
            f"<b>{group['name']}</b>\n\n"
            f"🎲 Сегодня смотрим:\n<b>{item['title']}</b>"
        )

    if edit:
        await message.edit_text(text, reply_markup=main_menu_keyboard())
    else:
        await message.answer(text, reply_markup=main_menu_keyboard())


@router.message(F.text == "📺 Что смотрим")
async def show_current(message: Message, repo: Repository) -> None:
    user = await _get_user_groups(message, repo)
    groups = await repo.get_user_groups(user["id"])

    if not groups:
        await message.answer(
            "У вас пока нет групп.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if len(groups) == 1:
        await _show_current_for_group(message, repo, groups[0]["id"])
        return

    await message.answer(
        "Выберите группу:",
        reply_markup=group_select_keyboard(groups, "current"),
    )


@router.callback_query(F.data.startswith("current:"))
async def show_current_for_group(callback: CallbackQuery, repo: Repository) -> None:
    group_id = int(callback.data.split(":")[1])
    user = await repo.get_user_by_telegram_id(callback.from_user.id)

    if not user or not await repo.is_group_member(group_id, user["id"]):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    await _show_current_for_group(callback.message, repo, group_id, edit=True)
    await callback.answer()


async def _show_current_for_group(
    message: Message,
    repo: Repository,
    group_id: int,
    edit: bool = False,
) -> None:
    group = await repo.get_group(group_id)
    item = await repo.get_current_watching(group_id)

    if item:
        text = (
            f"<b>{group['name']}</b>\n\n"
            f"📺 Сейчас смотрим:\n<b>{item['title']}</b>"
        )
    else:
        text = (
            f"<b>{group['name']}</b>\n\n"
            "Сейчас ничего не выбрано.\n"
            "Нажмите «🎬 Что посмотреть сегодня»."
        )

    if edit:
        await message.edit_text(text)
    else:
        await message.answer(text, reply_markup=main_menu_keyboard())


@router.message(F.text == "✅ Отметить просмотренным")
async def mark_completed(message: Message, repo: Repository) -> None:
    user = await _get_user_groups(message, repo)
    groups = await repo.get_user_groups(user["id"])

    if not groups:
        await message.answer(
            "У вас пока нет групп.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if len(groups) == 1:
        await _do_mark_completed(message, repo, groups[0]["id"])
        return

    await message.answer(
        "Выберите группу:",
        reply_markup=group_select_keyboard(groups, "complete"),
    )


@router.callback_query(F.data.startswith("complete:"))
async def mark_completed_for_group(callback: CallbackQuery, repo: Repository) -> None:
    group_id = int(callback.data.split(":")[1])
    user = await repo.get_user_by_telegram_id(callback.from_user.id)

    if not user or not await repo.is_group_member(group_id, user["id"]):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    await _do_mark_completed(callback.message, repo, group_id, edit=True)
    await callback.answer()


async def _do_mark_completed(
    message: Message,
    repo: Repository,
    group_id: int,
    edit: bool = False,
) -> None:
    group = await repo.get_group(group_id)
    item = await repo.mark_watching_completed(group_id)

    if item:
        text = (
            f"<b>{group['name']}</b>\n\n"
            f"✅ «{item['title']}» отмечен как просмотренный.\n"
            "Он больше не будет выпадать в случайном выборе."
        )
    else:
        text = (
            f"<b>{group['name']}</b>\n\n"
            "Нечего отмечать — сейчас ничего не выбрано для просмотра."
        )

    if edit:
        await message.edit_text(text)
    else:
        await message.answer(text, reply_markup=main_menu_keyboard())
