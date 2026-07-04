from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.handlers.common import (
    ensure_active_group,
    notify_group_members,
    set_active_and_get_group,
    upsert_user_from_callback,
    upsert_user_from_message,
)
from bot.handlers.utils import display_name
from bot.keyboards import (
    action_vote_keyboard,
    group_management_keyboard,
    group_select_keyboard,
    main_menu_keyboard,
    members_pick_keyboard,
    watch_items_pick_keyboard,
)
from bot.services.repository import Repository, normalize_username
from bot.states import AddMember

router = Router()


async def _send_action_votes(
    bot: Bot,
    repo: Repository,
    group_action: dict,
    initiator: dict,
    vote_text: str,
) -> None:
    members = await repo.get_group_members(group_action["group_id"])
    for member in members:
        if member["id"] == initiator["id"]:
            continue
        if group_action["action_type"] == "remove_member":
            if member["id"] == group_action["target_user_id"]:
                continue
        try:
            await bot.send_message(
                member["telegram_id"],
                vote_text,
                reply_markup=action_vote_keyboard(group_action["id"]),
            )
        except Exception:
            pass


@router.message(F.text == "🗑 Удалить из списка")
async def start_remove_item(message: Message, repo: Repository) -> None:
    user = await upsert_user_from_message(message, repo)
    group = await ensure_active_group(
        message, repo, user, callback_prefix="delgroup",
        prompt="Из какой группы удалить?",
    )
    if not group:
        return

    await _show_items_to_remove(message, repo, group["id"])


@router.callback_query(F.data.startswith("delgroup:"))
async def select_group_for_remove(callback: CallbackQuery, repo: Repository) -> None:
    group_id = int(callback.data.split(":")[1])
    user = await upsert_user_from_callback(callback, repo)

    if not await set_active_and_get_group(repo, user["id"], group_id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    await _show_items_to_remove(callback.message, repo, group_id, edit=True)
    await callback.answer()


async def _show_items_to_remove(
    message: Message,
    repo: Repository,
    group_id: int,
    edit: bool = False,
) -> None:
    group = await repo.get_group(group_id)
    items = await repo.get_watch_items(group_id)

    if not items:
        text = f"<b>{group['name']}</b>\n\nСписок пуст — удалять нечего."
        if edit:
            await message.edit_text(text)
        else:
            await message.answer(text, reply_markup=main_menu_keyboard())
        return

    text = (
        f"<b>{group['name']}</b>\n\n"
        "Выберите, что удалить из списка:\n"
        "(удаление — по согласию всех остальных участников)"
    )
    markup = watch_items_pick_keyboard(items)
    if edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("delpick:"))
async def propose_remove_item(
    callback: CallbackQuery,
    repo: Repository,
    bot: Bot,
) -> None:
    item_id = int(callback.data.split(":")[1])
    user = await upsert_user_from_callback(callback, repo)

    item = await repo.get_watch_item(item_id)
    if not item:
        await callback.answer("Элемент не найден.", show_alert=True)
        return

    if not await repo.is_group_member(item["group_id"], user["id"]):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    group = await repo.get_group(item["group_id"])
    group_action = await repo.create_group_action(
        group_id=item["group_id"],
        initiator_id=user["id"],
        action_type="remove_item",
        watch_item_id=item_id,
        title=item["title"],
    )

    initiator_label = display_name(user)
    vote_text = (
        f"🗑 {initiator_label} предлагает удалить из списка:\n"
        f"<b>{item['title']}</b>\n\n"
        f"Группа: {group['name']}\n"
        "Согласны?"
    )
    await _send_action_votes(bot, repo, group_action, user, vote_text)

    auto_result = await repo.try_auto_approve_action(group_action["id"])
    if auto_result:
        await callback.message.edit_text(
            f"✅ «{item['title']}» удалён из списка группы «{group['name']}»."
        )
        await callback.answer("Удалено!")
        return

    await callback.message.edit_text(
        f"✅ Запрос на удаление «<b>{item['title']}</b>» отправлен на голосование."
    )
    await callback.answer()


@router.message(F.text == "⚙️ Управление группой")
async def start_group_management(message: Message, repo: Repository) -> None:
    user = await upsert_user_from_message(message, repo)
    group = await ensure_active_group(
        message, repo, user, callback_prefix="mgmtgroup",
        prompt="Какой группой управлять?",
    )
    if not group:
        return

    await message.answer(
        f"<b>{group['name']}</b>\n\nВыберите действие:",
        reply_markup=group_management_keyboard(group["id"]),
    )


@router.callback_query(F.data.startswith("mgmtgroup:"))
async def select_group_for_management(callback: CallbackQuery, repo: Repository) -> None:
    group_id = int(callback.data.split(":")[1])
    user = await upsert_user_from_callback(callback, repo)

    group = await set_active_and_get_group(repo, user["id"], group_id)
    if not group:
        await callback.answer("Нет доступа.", show_alert=True)
        return

    await callback.message.edit_text(
        f"<b>{group['name']}</b>\n\nВыберите действие:",
        reply_markup=group_management_keyboard(group_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("mgmt:add:"))
async def start_add_member(
    callback: CallbackQuery,
    state: FSMContext,
    repo: Repository,
) -> None:
    group_id = int(callback.data.split(":")[2])
    user = await upsert_user_from_callback(callback, repo)

    if not await repo.is_group_member(group_id, user["id"]):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    await state.set_state(AddMember.waiting_username)
    await state.update_data(group_id=group_id)
    group = await repo.get_group(group_id)
    await callback.message.edit_text(
        f"Группа: <b>{group['name']}</b>\n\n"
        "Отправьте @username человека, которого хотите добавить.\n"
        "Он должен хотя бы раз написать боту /start.\n\n"
        "Добавление — по согласию всех текущих участников.\n"
        "Отмена: /cancel или любая кнопка меню",
    )
    await callback.answer()


@router.message(AddMember.waiting_username)
async def process_add_member(
    message: Message,
    state: FSMContext,
    repo: Repository,
    bot: Bot,
) -> None:
    data = await state.get_data()
    group_id = data.get("group_id")
    if not group_id:
        await state.clear()
        await message.answer("Ошибка. Начните заново.")
        return

    username = normalize_username(message.text or "")
    if not username:
        await message.answer("Не удалось распознать username. Пример: @friend")
        return

    user = await upsert_user_from_message(message, repo)
    target = await repo.get_user_by_username(username)

    if not target:
        await message.answer(
            f"Пользователь @{username} не найден.\n"
            "Он должен сначала написать боту /start."
        )
        return

    if await repo.is_group_member(group_id, target["id"]):
        await message.answer("Этот пользователь уже в группе.")
        return

    group = await repo.get_group(group_id)
    group_action = await repo.create_group_action(
        group_id=group_id,
        initiator_id=user["id"],
        action_type="add_member",
        target_user_id=target["id"],
        title=display_name(target),
    )

    await state.clear()

    initiator_label = display_name(user)
    target_label = display_name(target)
    vote_text = (
        f"➕ {initiator_label} предлагает добавить в группу:\n"
        f"<b>{target_label}</b>\n\n"
        f"Группа: {group['name']}\n"
        "Согласны?"
    )
    await _send_action_votes(bot, repo, group_action, user, vote_text)

    await message.answer(
        f"✅ Запрос на добавление {target_label} отправлен на голосование.",
        reply_markup=main_menu_keyboard(),
    )


@router.callback_query(F.data.startswith("mgmt:remove:"))
async def start_remove_member(callback: CallbackQuery, repo: Repository) -> None:
    group_id = int(callback.data.split(":")[2])
    user = await upsert_user_from_callback(callback, repo)

    if not await repo.is_group_member(group_id, user["id"]):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    members = await repo.get_group_members(group_id)
    if len(members) < 2:
        await callback.answer("В группе только один участник.", show_alert=True)
        return

    group = await repo.get_group(group_id)
    await callback.message.edit_text(
        f"<b>{group['name']}</b>\n\n"
        "Кого исключить?\n"
        "(нужно согласие всех, кроме исключаемого)",
        reply_markup=members_pick_keyboard(members, prefix=f"rmpick:{group_id}"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rmpick:"))
async def propose_remove_member(
    callback: CallbackQuery,
    repo: Repository,
    bot: Bot,
) -> None:
    parts = callback.data.split(":")
    group_id = int(parts[1])
    target_user_id = int(parts[2])
    user = await upsert_user_from_callback(callback, repo)

    if not await repo.is_group_member(group_id, user["id"]):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    group_members = await repo.get_group_members(group_id)
    target = next((m for m in group_members if m["id"] == target_user_id), None)
    if not target:
        await callback.answer("Участник не найден.", show_alert=True)
        return

    group = await repo.get_group(group_id)
    group_action = await repo.create_group_action(
        group_id=group_id,
        initiator_id=user["id"],
        action_type="remove_member",
        target_user_id=target_user_id,
        title=display_name(target),
    )

    initiator_label = display_name(user)
    target_label = display_name(target)
    vote_text = (
        f"➖ {initiator_label} предлагает исключить из группы:\n"
        f"<b>{target_label}</b>\n\n"
        f"Группа: {group['name']}\n"
        "Согласны?"
    )
    await _send_action_votes(bot, repo, group_action, user, vote_text)

    await callback.message.edit_text(
        f"✅ Запрос на исключение {target_label} отправлен на голосование."
    )
    await callback.answer()


@router.callback_query(F.data.startswith("action:"))
async def handle_action_vote(
    callback: CallbackQuery,
    repo: Repository,
    bot: Bot,
) -> None:
    parts = callback.data.split(":")
    approved = parts[1] == "approve"
    action_id = int(parts[2])

    user = await upsert_user_from_callback(callback, repo)
    result = await repo.vote_on_group_action(action_id, user["id"], approved)

    if not result:
        await callback.answer("Голосование недоступно.", show_alert=True)
        return

    group_action = result["group_action"]
    group = await repo.get_group(group_action["group_id"])
    voter_label = display_name(user)

    if result["action"] == "rejected":
        await callback.message.edit_text(f"{voter_label} не согласен.\nЗапрос отклонён.")
        await callback.answer("Голос учтён")
        return

    if result["action"] == "vote_recorded":
        await callback.message.edit_text(
            f"✅ {voter_label} согласен.\n"
            "Ждём голосов остальных участников."
        )
        await callback.answer("Голос учтён")
        return

    executed = result.get("executed")
    if executed == "remove_item":
        notify = f"🗑 «<b>{group_action['title']}</b>» удалён из списка группы «{group['name']}»."
        await notify_group_members(bot, repo, group_action["group_id"], notify)
        await callback.message.edit_text(
            f"✅ {voter_label} согласен — все проголосовали!\n"
            f"«{group_action['title']}» удалён из списка."
        )

    elif executed == "add_member":
        target = result["target_user"]
        target_label = display_name(target)
        notify = f"🎉 {target_label} добавлен в группу «{group['name']}»!"
        await notify_group_members(bot, repo, group_action["group_id"], notify)
        try:
            await bot.send_message(
                target["telegram_id"],
                f"📬 Вас добавили в группу «{group['name']}»!\n"
                "Теперь можно предлагать фильмы и голосовать.",
                reply_markup=main_menu_keyboard(),
            )
        except Exception:
            pass
        await callback.message.edit_text(
            f"✅ {voter_label} согласен — все проголосовали!\n"
            f"{target_label} добавлен в группу."
        )

    elif executed == "remove_member":
        target = result["target_user"]
        target_label = display_name(target)
        notify = f"👤 {target_label} исключён из группы «{group['name']}»."
        await notify_group_members(
            bot,
            repo,
            group_action["group_id"],
            notify,
            exclude_user_ids={target["id"]},
        )
        try:
            await bot.send_message(
                target["telegram_id"],
                f"ℹ️ Вас исключили из группы «{group['name']}».",
                reply_markup=main_menu_keyboard(),
            )
        except Exception:
            pass
        await callback.message.edit_text(
            f"✅ {voter_label} согласен — все проголосовали!\n"
            f"{target_label} исключён из группы."
        )

    await callback.answer("Готово!")
