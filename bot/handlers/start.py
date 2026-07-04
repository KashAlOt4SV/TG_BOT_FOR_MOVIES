from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.handlers.help_text import HELP_TEXT
from bot.keyboards import main_menu_keyboard
from bot.services.repository import Repository

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, repo: Repository) -> None:
    user = await repo.upsert_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    pending = await repo.get_pending_invites_for_user(user["id"])
    invite_hint = ""
    if pending:
        invite_hint = f"\n\n📬 У вас {len(pending)} новых приглашений — проверьте сообщения выше."

    await message.answer(
        "Привет! 👋\n\n"
        "Я помогу вам с близкими и друзьями выбирать, что смотреть.\n\n"
        "Нажмите «🤝 Создать группу», чтобы объединиться с другими, "
        "или используйте меню ниже."
        f"{invite_hint}",
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command("help"))
@router.message(F.text == "❓ Помощь")
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT, reply_markup=main_menu_keyboard())


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current is None:
        await message.answer("Нечего отменять.", reply_markup=main_menu_keyboard())
        return
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=main_menu_keyboard())


@router.callback_query(F.data == "cancel")
async def callback_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Отменено.")
    await callback.answer()
