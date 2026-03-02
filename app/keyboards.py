from telebot import types

from app import state


def build_reply_kb(options) -> types.ReplyKeyboardMarkup:
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for option in options:
        keyboard.add(types.KeyboardButton(str(option)))
    return keyboard


def build_toggle_kb(options, selected_set, prefix: str) -> types.InlineKeyboardMarkup:
    keyboard = types.InlineKeyboardMarkup()
    row = []
    for option in options:
        label = f"✅ {option}" if option in selected_set else option
        row.append(types.InlineKeyboardButton(label, callback_data=f"{prefix}:{option}"))
        if len(row) == 2:
            keyboard.row(*row)
            row = []
    if row:
        keyboard.row(*row)
    return keyboard


def build_locations_kb(profile: dict) -> types.InlineKeyboardMarkup:
    selected = set(profile.get("locations") or [])
    any_selected = bool(profile.get("locations_any"))
    keyboard = types.InlineKeyboardMarkup()
    row = []
    for option in state.LOCATION_OPTIONS:
        is_selected = any_selected if option == "Не важно" else option in selected
        label = f"✅ {option}" if is_selected else option
        row.append(types.InlineKeyboardButton(label, callback_data=f"loc:{option}"))
        if len(row) == 2:
            keyboard.row(*row)
            row = []
    if row:
        keyboard.row(*row)
    return keyboard


def build_experience_kb(profile: dict) -> types.InlineKeyboardMarkup:
    selected = profile.get("experience")
    keyboard = types.InlineKeyboardMarkup()
    row = []
    for option in state.EXPERIENCE_OPTIONS:
        label = f"✅ {option}" if option == selected else option
        row.append(types.InlineKeyboardButton(label, callback_data=f"exp:{option}"))
        if len(row) == 2:
            keyboard.row(*row)
            row = []
    if row:
        keyboard.row(*row)
    return keyboard


def build_main_menu() -> types.ReplyKeyboardMarkup:
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.row(types.KeyboardButton("📄 Резюме"), types.KeyboardButton("👀 Вакансии"))
    return keyboard


def build_edit_menu() -> types.InlineKeyboardMarkup:
    keyboard = types.InlineKeyboardMarkup()
    items = [
        ("desired_role", "Должность"),
        ("work_format", "Формат"),
        ("locations", "Локация"),
        ("min_salary", "Зарплата"),
        ("experience", "Опыт"),
        ("skills", "Навыки"),
        ("stop_words", "Стоп-слова"),
        ("blacklisted_companies", "Компании"),
    ]
    row = []
    for key, label in items:
        row.append(types.InlineKeyboardButton(label, callback_data=f"edit:{key}"))
        if len(row) == 2:
            keyboard.row(*row)
            row = []
    if row:
        keyboard.row(*row)
    keyboard.row(types.InlineKeyboardButton("⬅️ Назад", callback_data="edit:cancel"))
    return keyboard


def build_vacancy_kb(vacancy: dict) -> types.InlineKeyboardMarkup:
    keyboard = types.InlineKeyboardMarkup()
    row = []
    if vacancy.get("url"):
        row.append(types.InlineKeyboardButton("Открыть", url=vacancy["url"]))
    row.append(types.InlineKeyboardButton("Следующая ➡️", callback_data="vac:next"))
    if row:
        keyboard.row(*row)
    return keyboard
