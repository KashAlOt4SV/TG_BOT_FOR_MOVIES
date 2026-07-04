from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

MAIN_MENU_BUTTONS = [
    ["🎬 Что посмотреть сегодня", "📺 Что смотрим"],
    ["➕ Предложить фильм", "✅ Отметить просмотренным"],
    ["👥 Мои группы", "📋 Списки"],
    ["🤝 Создать группу", "❓ Помощь"],
]


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=btn) for btn in row] for row in MAIN_MENU_BUTTONS],
        resize_keyboard=True,
    )


def group_select_keyboard(groups: list[dict], prefix: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(
            text=f"{g['name']} ({g['member_count']} чел.)",
            callback_data=f"{prefix}:{g['id']}",
        )]
        for g in groups
    ]
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def invite_keyboard(invite_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Принять",
                    callback_data=f"invite:accept:{invite_id}",
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"invite:reject:{invite_id}",
                ),
            ]
        ]
    )


def proposal_vote_keyboard(proposal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👍 Согласен",
                    callback_data=f"proposal:approve:{proposal_id}",
                ),
                InlineKeyboardButton(
                    text="👎 Не согласен",
                    callback_data=f"proposal:reject:{proposal_id}",
                ),
            ]
        ]
    )


def group_detail_keyboard(group_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📋 Список на просмотр",
                    callback_data=f"list:queued:{group_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📺 Сейчас смотрим",
                    callback_data=f"list:watching:{group_id}",
                ),
                InlineKeyboardButton(
                    text="✅ Просмотрено",
                    callback_data=f"list:completed:{group_id}",
                ),
            ],
        ]
    )
