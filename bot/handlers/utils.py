def display_name(user: dict) -> str:
    if user.get("username"):
        return f"@{user['username']}"
    return user.get("first_name") or "Пользователь"
