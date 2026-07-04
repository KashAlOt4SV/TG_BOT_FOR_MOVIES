from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

MAIN_MENU_BUTTONS = [
    ["🎬 Что посмотреть сегодня", "📺 Что смотрим"],
    ["➕ Предложить фильм", "🗑 Удалить из списка"],
    ["✅ Отметить просмотренным", "📋 Списки"],
    ["🔄 Сменить группу", "🤝 Создать группу"],
    ["👥 Мои группы", "⚙️ Управление группой"],
    ["❓ Помощь"],
]

MENU_BUTTON_TEXTS = frozenset(btn for row in MAIN_MENU_BUTTONS for btn in row)


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=btn) for btn in row] for row in MAIN_MENU_BUTTONS],
        resize_keyboard=True,
    )


def group_select_keyboard(
    groups: list[dict],
    prefix: str,
    active_group_id: int | None = None,
) -> InlineKeyboardMarkup:
    buttons = []
    for g in groups:
        marker = "✓ " if g["id"] == active_group_id else ""
        buttons.append([InlineKeyboardButton(
            text=f"{marker}{g['name']} ({g['member_count']} чел.)",
            callback_data=f"{prefix}:{g['id']}",
        )])
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


def action_vote_keyboard(action_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👍 Согласен",
                    callback_data=f"action:approve:{action_id}",
                ),
                InlineKeyboardButton(
                    text="👎 Не согласен",
                    callback_data=f"action:reject:{action_id}",
                ),
            ]
        ]
    )


def group_management_keyboard(group_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Добавить участника",
                    callback_data=f"mgmt:add:{group_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="➖ Исключить участника",
                    callback_data=f"mgmt:remove:{group_id}",
                ),
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
        ]
    )


def watch_items_pick_keyboard(items: list[dict], prefix: str = "delpick") -> InlineKeyboardMarkup:
    buttons = []
    for item in items[:25]:
        title = item["title"]
        if len(title) > 45:
            title = title[:42] + "..."
        status_mark = {"watching": "📺 ", "completed": "✅ ", "queued": ""}.get(item["status"], "")
        buttons.append([
            InlineKeyboardButton(
                text=f"{status_mark}{title}",
                callback_data=f"{prefix}:{item['id']}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def members_pick_keyboard(
    members: list[dict],
    prefix: str = "rmpick",
) -> InlineKeyboardMarkup:
    buttons = []
    for member in members:
        name = member.get("username") or member.get("first_name") or "?"
        if member.get("username"):
            name = f"@{member['username']}"
        buttons.append([
            InlineKeyboardButton(
                text=name,
                callback_data=f"{prefix}:{member['id']}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


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
