from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards import group_select_keyboard, invite_keyboard, main_menu_keyboard
from bot.services.repository import Repository, parse_usernames
from bot.states import GroupCreation

router = Router()


def _display_name(user: dict) -> str:
    if user.get("username"):
        return f"@{user['username']}"
    return user.get("first_name") or "Пользователь"


@router.message(F.text == "🤝 Создать группу")
async def start_group_creation(message: Message, state: FSMContext) -> None:
    await state.set_state(GroupCreation.waiting_usernames)
    await message.answer(
        "Отправьте @username людей, с которыми хотите создать группу.\n\n"
        "Пример: <code>@wife @friend</code>\n\n"
        "⚠️ Каждый приглашённый должен хотя бы раз написать боту /start.\n"
        "Отмена: /cancel",
    )


@router.message(GroupCreation.waiting_usernames)
async def process_usernames(
    message: Message,
    state: FSMContext,
    repo: Repository,
    bot: Bot,
) -> None:
    creator = await repo.upsert_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    usernames = parse_usernames(message.text or "")
    if not usernames:
        await message.answer(
            "Не удалось распознать username. Попробуйте снова, например: @friend"
        )
        return

    own_username = (creator.get("username") or "").lower()
    if own_username in usernames:
        usernames.remove(own_username)

    if not usernames:
        await message.answer("Укажите username других людей, не только свой.")
        return

    found_users: list[dict] = []
    not_found: list[str] = []

    for username in usernames:
        user = await repo.get_user_by_username(username)
        if user:
            if user["id"] != creator["id"]:
                found_users.append(user)
        else:
            not_found.append(f"@{username}")

    if not found_users:
        await message.answer(
            "Никого из указанных пользователей не найдено.\n\n"
            "Они должны сначала написать боту /start, "
            f"чтобы бот узнал их username.\n\n"
            f"Не найдены: {', '.join(not_found)}"
        )
        return

    formation = await repo.create_formation(
        creator_id=creator["id"],
        invitee_ids=[u["id"] for u in found_users],
    )

    await state.clear()

    creator_label = _display_name(creator)
    for invitee in found_users:
        invite_row = await repo.get_invite_for_formation(formation["id"], invitee["id"])
        if not invite_row:
            continue
        try:
            await bot.send_message(
                invitee["telegram_id"],
                f"📬 {creator_label} приглашает вас в группу для совместного выбора фильмов!\n\n"
                "Примите приглашение, чтобы начать добавлять фильмы в общий список.",
                reply_markup=invite_keyboard(invite_row["id"]),
            )
        except Exception:
            pass

    lines = [f"✅ Приглашения отправлены ({len(found_users)} чел.):"]
    for u in found_users:
        lines.append(f"  • {_display_name(u)}")

    if not_found:
        lines.append("")
        lines.append("⚠️ Не найдены (нужен /start в боте):")
        for name in not_found:
            lines.append(f"  • {name}")

    lines.append("")
    lines.append("Группа создастся, когда все примут приглашение.")

    await message.answer("\n".join(lines), reply_markup=main_menu_keyboard())


@router.callback_query(F.data.startswith("invite:"))
async def handle_invite_response(
    callback: CallbackQuery,
    repo: Repository,
    bot: Bot,
) -> None:
    parts = callback.data.split(":")
    action = parts[1]
    invite_id = int(parts[2])
    accepted = action == "accept"

    user = await repo.upsert_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )

    result = await repo.respond_to_invite(invite_id, user["id"], accepted)

    if not result:
        await callback.answer("Приглашение уже обработано или недоступно.", show_alert=True)
        return

    if result["action"] == "rejected":
        await callback.message.edit_text("Вы отклонили приглашение.")
        await callback.answer()
        return

    if result["action"] == "accepted_pending":
        await callback.message.edit_text("✅ Вы приняли приглашение! Ждём остальных участников.")
        await callback.answer("Приглашение принято!")
        return

    group = result["group"]
    formation_id = result["formation_id"]
    telegram_ids = await repo.get_formation_participants_telegram_ids(formation_id)

    notify_text = (
        f"🎉 Группа «{group['name']}» создана!\n\n"
        "Теперь можно предлагать фильмы через «➕ Предложить фильм»."
    )

    for tg_id in telegram_ids:
        try:
            await bot.send_message(tg_id, notify_text, reply_markup=main_menu_keyboard())
        except Exception:
            pass

    await callback.message.edit_text(f"✅ Группа «{group['name']}» создана!")
    await callback.answer("Группа создана!")


@router.message(F.text == "👥 Мои группы")
async def show_my_groups(message: Message, repo: Repository) -> None:
    user = await repo.upsert_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    groups = await repo.get_user_groups(user["id"])

    if not groups:
        await message.answer(
            "У вас пока нет групп.\nНажмите «🤝 Создать группу», чтобы начать.",
            reply_markup=main_menu_keyboard(),
        )
        return

    lines = ["<b>👥 Ваши группы:</b>\n"]
    for g in groups:
        members = await repo.get_group_members(g["id"])
        member_names = ", ".join(_display_name(m) for m in members)
        lines.append(f"• <b>{g['name']}</b> ({g['member_count']} чел.)")
        lines.append(f"  {member_names}\n")

    await message.answer("\n".join(lines), reply_markup=main_menu_keyboard())
