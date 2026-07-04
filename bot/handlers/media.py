from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.handlers.common import (
    active_group_label,
    ensure_active_group,
    notify_group_members,
    set_active_and_get_group,
    upsert_user_from_callback,
    upsert_user_from_message,
)
from bot.handlers.utils import display_name
from bot.keyboards import main_menu_keyboard, proposal_vote_keyboard
from bot.services.movie_lookup import MovieLookupService, format_lookup_message
from bot.services.repository import Repository
from bot.states import MediaProposal

router = Router()


@router.message(F.text == "➕ Предложить фильм")
async def start_proposal(message: Message, state: FSMContext, repo: Repository) -> None:
    user = await upsert_user_from_message(message, repo)
    group = await ensure_active_group(
        message, repo, user, callback_prefix="propose",
        prompt="Для какой группы предложить фильм?",
    )
    if not group:
        return

    await state.set_state(MediaProposal.waiting_title)
    await state.update_data(group_id=group["id"])
    await message.answer(
        f"Группа: <b>{group['name']}</b>\n\n"
        "Отправьте название фильма, сериала или аниме.\n"
        "Отмена: /cancel или любая кнопка меню",
    )


@router.callback_query(F.data.startswith("propose:"))
async def select_group_for_proposal(
    callback: CallbackQuery,
    state: FSMContext,
    repo: Repository,
) -> None:
    group_id = int(callback.data.split(":")[1])
    user = await upsert_user_from_callback(callback, repo)

    group = await set_active_and_get_group(repo, user["id"], group_id)
    if not group:
        await callback.answer("Нет доступа к этой группе.", show_alert=True)
        return

    await state.set_state(MediaProposal.waiting_title)
    await state.update_data(group_id=group_id)
    await callback.message.edit_text(
        f"Группа: <b>{group['name']}</b>\n\n"
        "Отправьте название фильма, сериала или аниме.\n"
        "Отмена: /cancel или любая кнопка меню",
    )
    await callback.answer()


@router.message(MediaProposal.waiting_title)
async def process_proposal_title(
    message: Message,
    state: FSMContext,
    repo: Repository,
    bot: Bot,
) -> None:
    title = (message.text or "").strip()
    if not title or len(title) < 2:
        await message.answer("Название слишком короткое. Попробуйте ещё раз.")
        return
    if len(title) > 200:
        await message.answer("Название слишком длинное (макс. 200 символов).")
        return

    data = await state.get_data()
    group_id = data.get("group_id")
    if not group_id:
        await state.clear()
        await message.answer("Ошибка: группа не выбрана. Начните заново.")
        return

    user = await upsert_user_from_message(message, repo)
    proposal = await repo.create_media_proposal(group_id, user["id"], title)
    group = await repo.get_group(group_id)
    members = await repo.get_group_members(group_id)

    await state.clear()

    proposer_label = display_name(user)
    await message.answer(
        f"✅ Предложение «<b>{title}</b>» отправлено на голосование "
        f"в группе «{group['name']}».",
        reply_markup=main_menu_keyboard(),
    )

    vote_text = (
        f"🎬 {proposer_label} предлагает посмотреть:\n"
        f"<b>{title}</b>\n\n"
        f"Группа: {group['name']}\n"
        "Согласны добавить в список?"
    )

    for member in members:
        if member["id"] == user["id"]:
            continue
        try:
            await bot.send_message(
                member["telegram_id"],
                vote_text,
                reply_markup=proposal_vote_keyboard(proposal["id"]),
            )
        except Exception:
            pass


@router.callback_query(F.data.startswith("proposal:info:"))
async def show_proposal_info(
    callback: CallbackQuery,
    repo: Repository,
    movie_lookup: MovieLookupService,
) -> None:
    proposal_id = int(callback.data.split(":")[2])
    user = await upsert_user_from_callback(callback, repo)

    proposal = await repo.get_proposal(proposal_id)
    if not proposal:
        await callback.answer("Предложение не найдено.", show_alert=True)
        return

    if not await repo.is_group_member(proposal["group_id"], user["id"]):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    await callback.answer("Ищу информацию…")

    members = await repo.get_group_members(proposal["group_id"])
    proposer = next(
        (m for m in members if m["id"] == proposal["proposer_id"]),
        None,
    )
    proposer_label = display_name(proposer) if proposer else None

    result = await movie_lookup.lookup(proposal["title"])
    text = format_lookup_message(result, proposer_hint=proposer_label)
    await callback.message.answer(text)


@router.callback_query(F.data.startswith("proposal:"))
async def handle_proposal_vote(
    callback: CallbackQuery,
    repo: Repository,
    bot: Bot,
) -> None:
    parts = callback.data.split(":")
    action = parts[1]
    if action == "info":
        return
    proposal_id = int(parts[2])
    approved = action == "approve"

    user = await upsert_user_from_callback(callback, repo)
    result = await repo.vote_on_proposal(proposal_id, user["id"], approved)
    if not result:
        await callback.answer("Голосование недоступно.", show_alert=True)
        return

    proposal = result["proposal"]
    group = await repo.get_group(proposal["group_id"])
    voter_label = display_name(user)

    if result["action"] == "rejected":
        members = await repo.get_group_members(proposal["group_id"])
        proposer = next(
            (m for m in members if m["id"] == proposal["proposer_id"]),
            None,
        )
        proposer_label = display_name(proposer) if proposer else "участник"

        reject_notify = (
            f"❌ {voter_label} отказался от просмотра:\n"
            f"<b>{proposal['title']}</b>\n\n"
            f"Группа: {group['name']}\n"
            f"Предложил: {proposer_label}"
        )
        await notify_group_members(
            bot,
            repo,
            proposal["group_id"],
            reject_notify,
            exclude_user_ids={user["id"]},
        )

        await callback.message.edit_text(
            f"{voter_label} не согласен.\n"
            f"Предложение «{proposal['title']}» отклонено."
        )
        await callback.answer("Голос учтён")
        return

    if result["action"] == "vote_recorded":
        await callback.message.edit_text(
            f"✅ {voter_label} согласен с «{proposal['title']}».\n"
            "Ждём голосов остальных участников."
        )
        await callback.answer("Голос учтён")
        return

    members = await repo.get_group_members(proposal["group_id"])
    notify = (
        f"🎉 «<b>{proposal['title']}</b>» добавлен в список группы «{group['name']}»!\n"
        "Можно выбирать через «🎬 Что посмотреть сегодня»."
    )
    await notify_group_members(bot, repo, proposal["group_id"], notify)

    await callback.message.edit_text(
        f"✅ {voter_label} согласен — все проголосовали!\n"
        f"«{proposal['title']}» добавлен в список."
    )
    await callback.answer("Добавлено в список!")


@router.message(F.text == "📋 Списки")
async def show_lists_menu(message: Message, repo: Repository) -> None:
    user = await upsert_user_from_message(message, repo)
    group = await ensure_active_group(
        message, repo, user, callback_prefix="lists",
        prompt="Списки какой группы показать?",
    )
    if not group:
        return

    await _send_group_lists(message, repo, group["id"])


@router.callback_query(F.data.startswith("lists:"))
async def select_group_for_lists(callback: CallbackQuery, repo: Repository) -> None:
    group_id = int(callback.data.split(":")[1])
    user = await upsert_user_from_callback(callback, repo)

    if not await set_active_and_get_group(repo, user["id"], group_id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    await _send_group_lists(callback.message, repo, group_id, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("list:"))
async def show_list_section(callback: CallbackQuery, repo: Repository) -> None:
    parts = callback.data.split(":")
    status = parts[1]
    group_id = int(parts[2])

    user = await upsert_user_from_callback(callback, repo)
    if not await repo.is_group_member(group_id, user["id"]):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    group = await repo.get_group(group_id)
    items = await repo.get_watch_items(group_id, status=status)

    status_titles = {
        "queued": "📋 Очередь на просмотр",
        "watching": "📺 Сейчас смотрим",
        "completed": "✅ Просмотрено",
        "dropped": "🚫 Бросили",
    }

    if not items:
        text = f"<b>{group['name']}</b>\n{status_titles[status]}\n\nСписок пуст."
    else:
        lines = [f"<b>{group['name']}</b>", status_titles[status], ""]
        for i, item in enumerate(items, 1):
            lines.append(f"{i}. {item['title']}")
        text = "\n".join(lines)

    from bot.keyboards import group_detail_keyboard
    await callback.message.edit_text(text, reply_markup=group_detail_keyboard(group_id))
    await callback.answer()


async def _send_group_lists(
    message: Message,
    repo: Repository,
    group_id: int,
    edit: bool = False,
) -> None:
    from bot.keyboards import group_detail_keyboard

    group = await repo.get_group(group_id)
    queued = await repo.get_watch_items(group_id, "queued")
    watching = await repo.get_watch_items(group_id, "watching")
    completed = await repo.get_watch_items(group_id, "completed")
    dropped = await repo.get_watch_items(group_id, "dropped")

    lines = [f"<b>{active_group_label(group)}</b>", ""]

    lines.append(f"📺 Сейчас смотрим: {watching[0]['title'] if watching else '—'}")
    lines.append("")

    lines.append(f"📋 В очереди ({len(queued)}):")
    if queued:
        for i, item in enumerate(queued[:15], 1):
            lines.append(f"  {i}. {item['title']}")
        if len(queued) > 15:
            lines.append(f"  ... и ещё {len(queued) - 15}")
    else:
        lines.append("  —")

    lines.append("")
    lines.append(f"✅ Просмотрено ({len(completed)}):")
    if completed:
        for i, item in enumerate(completed[-10:], 1):
            lines.append(f"  {i}. {item['title']}")
        if len(completed) > 10:
            lines.append(f"  (показаны последние 10 из {len(completed)})")
    else:
        lines.append("  —")

    lines.append("")
    lines.append(f"🚫 Бросили ({len(dropped)}):")
    if dropped:
        for i, item in enumerate(dropped[-10:], 1):
            lines.append(f"  {i}. {item['title']}")
        if len(dropped) > 10:
            lines.append(f"  (показаны последние 10 из {len(dropped)})")
    else:
        lines.append("  —")

    text = "\n".join(lines)
    markup = group_detail_keyboard(group_id)

    if edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)
