import copy

from telebot import types

from app import state
from app.config import Settings
from app.keyboards import (
    build_edit_menu,
    build_experience_kb,
    build_locations_kb,
    build_main_menu,
    build_reply_kb,
    build_toggle_kb,
    build_vacancy_kb,
)
from app.services.matching import normalize_skills_list
from app.services.profile_store import get_profile_for_user, persist_profile
from app.services.vacancies import build_vacancy_text, enrich_hh_vacancy, format_fetch_info, get_next_vacancy, mark_vacancy_seen
from app.utils.text import format_value, parse_list, parse_salary


def register_handlers(bot, settings: Settings) -> None:
    def show_main_menu(chat_id: int) -> None:
        bot.send_message(chat_id, "Ок.", reply_markup=build_main_menu())

    def show_edit_menu(chat_id: int) -> None:
        bot.send_message(chat_id, "Что изменить?", reply_markup=build_edit_menu())

    def format_profile_text(profile: dict) -> str:
        role = profile.get("desired_role") or "не указана"
        work_formats = format_value(profile.get("work_formats"))
        locations = "не важно" if profile.get("locations_any") else format_value(profile.get("locations"))
        min_salary = format_value(profile.get("min_salary"))
        experience = format_value(profile.get("experience"))
        skills = format_value(profile.get("skills"))
        stop_words = format_value(profile.get("stop_words"))
        companies = format_value(profile.get("blacklisted_companies"))
        return (
            "<b>Профиль:</b>\n"
            f"Должность: {role}\n"
            f"Формат: {work_formats}\n"
            f"Города: {locations}\n"
            f"Мин. бюджет: {min_salary}\n"
            f"Опыт: {experience}\n"
            f"\nНавыки: {skills}\n"
            f"\nСтоп-слова: {stop_words}\n"
            f"Чёрный список: {companies}"
        )

    def send_profile_text(chat_id: int, profile: dict, with_confirm: bool = False, with_edit: bool = False, with_restart: bool = False) -> None:
        keyboard = None
        if with_confirm or with_edit or with_restart:
            keyboard = types.InlineKeyboardMarkup()
            row = []
            if with_confirm:
                row.append(types.InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_profile"))
            if with_edit:
                row.append(types.InlineKeyboardButton("✏️ Изменить", callback_data="edit_menu"))
            if with_restart:
                row.append(types.InlineKeyboardButton("🔁 Заново", callback_data="profile_restart"))
            if row:
                keyboard.row(*row)
        bot.send_message(chat_id, format_profile_text(profile), reply_markup=keyboard)

    def start_onboarding(chat_id: int, tg_id: int) -> None:
        state.user_state[tg_id] = {"step": 0, "profile": copy.deepcopy(state.DEFAULT_PROFILE), "mode": "onboarding"}
        ask_next_step(chat_id, tg_id)

    def start_editing(chat_id: int, tg_id: int, step_key: str) -> None:
        profile = get_profile_for_user(tg_id, settings)
        if not profile:
            bot.send_message(chat_id, "Профиль ещё не заполнен. Нажми /start.")
            return
        if step_key not in state.STEPS:
            bot.send_message(chat_id, "Неизвестный раздел.")
            return
        state.user_state[tg_id] = {"step": state.STEPS.index(step_key), "profile": profile, "mode": "edit"}
        ask_next_step(chat_id, tg_id)

    def ask_next_step(chat_id: int, tg_id: int) -> None:
        current_state = state.user_state[tg_id]
        step = state.STEPS[current_state["step"]]
        profile = current_state["profile"]
        if step == "desired_role":
            bot.send_message(chat_id, "Введи желаемую должность:", reply_markup=types.ReplyKeyboardRemove())
            return
        if step == "work_format":
            bot.send_message(chat_id, "Выбери формат работы (можно несколько):", reply_markup=build_toggle_kb(state.WORK_FORMAT_OPTIONS, set(profile.get("work_formats") or []), "wf"))
            bot.send_message(chat_id, "Когда готов — нажми «Далее».", reply_markup=build_reply_kb(["Далее"]))
            return
        if step == "locations":
            bot.send_message(chat_id, "Выбери локации (можно несколько) или «Не важно».", reply_markup=build_locations_kb(profile))
            bot.send_message(chat_id, "Когда готов — нажми «Далее».", reply_markup=build_reply_kb(["Далее"]))
            return
        if step == "min_salary":
            bot.send_message(chat_id, "Минимальный бюджет? (число, в рублях). Можно пропустить.", reply_markup=build_reply_kb(["Пропустить"]))
            return
        if step == "experience":
            bot.send_message(chat_id, "Выбери опыт (только один):", reply_markup=build_experience_kb(profile))
            bot.send_message(chat_id, "Когда готов — нажми «Далее».", reply_markup=build_reply_kb(["Далее"]))
            return
        if step == "skills":
            bot.send_message(chat_id, "Навыки (ключевые слова через запятую). Можно пропустить.", reply_markup=build_reply_kb(["Пропустить"]))
            return
        if step == "stop_words":
            bot.send_message(chat_id, "Стоп-слова через запятую. Можно пропустить.", reply_markup=build_reply_kb(["Пропустить"]))
            return
        if step == "blacklisted_companies":
            bot.send_message(chat_id, "Чёрный список компаний через запятую. Можно пропустить.", reply_markup=build_reply_kb(["Пропустить"]))

    def send_profile_summary(chat_id: int, tg_id: int) -> None:
        profile = state.user_state[tg_id]["profile"]
        bot.send_message(chat_id, "Проверь профиль:", reply_markup=types.ReplyKeyboardRemove())
        send_profile_text(chat_id, profile, with_confirm=True, with_edit=True, with_restart=True)

    def finish_step(chat_id: int, tg_id: int) -> None:
        current_state = state.user_state[tg_id]
        profile = current_state["profile"]
        if current_state.get("mode") == "edit":
            persist_profile(tg_id, profile, settings)
            state.user_state.pop(tg_id, None)
            send_profile_text(chat_id, profile, with_edit=True, with_restart=True)
            bot.send_message(chat_id, "Профиль обновлён.", reply_markup=build_main_menu())
            return
        current_state["step"] += 1
        if current_state["step"] >= len(state.STEPS):
            send_profile_summary(chat_id, tg_id)
        else:
            ask_next_step(chat_id, tg_id)

    def show_resume(message, user_id: int | None = None) -> None:
        uid = user_id if user_id is not None else message.from_user.id
        profile = get_profile_for_user(uid, settings)
        if not profile:
            bot.send_message(message.chat.id, "Профиль ещё не заполнен. Нажми /start.")
            return
        send_profile_text(message.chat.id, profile, with_edit=True, with_restart=True)

    def send_vacancy(chat_id: int, tg_id: int) -> None:
        vacancy = get_next_vacancy(tg_id, settings)
        if not vacancy:
            info = format_fetch_info(state.last_fetch_info.get(tg_id))
            bot.send_message(chat_id, info or "Пока новых заказов нет. Попробуй позже.", reply_markup=build_main_menu())
            return
        profile = get_profile_for_user(tg_id, settings)
        if profile and vacancy.get("source") == "hh":
            vacancy = enrich_hh_vacancy(profile, vacancy, settings)
        mark_vacancy_seen(tg_id, vacancy, settings)
        bot.send_message(chat_id, build_vacancy_text(vacancy), reply_markup=build_vacancy_kb(vacancy))

    def show_vacancies(message, user_id: int | None = None) -> None:
        uid = user_id if user_id is not None else message.from_user.id
        if not get_profile_for_user(uid, settings):
            bot.send_message(message.chat.id, "Сначала заполни профиль: /start.")
            return
        send_vacancy(message.chat.id, uid)

    @bot.message_handler(commands=["start"])
    def handle_start(message):
        tg_id = message.from_user.id
        profile = get_profile_for_user(tg_id, settings)
        if profile:
            bot.reply_to(message, "Привет! Я тебя помню — вот твой профиль:", reply_markup=build_main_menu())
            send_profile_text(message.chat.id, profile, with_edit=True, with_restart=True)
            return
        bot.reply_to(message, "Привет! Давай настроим профиль.")
        start_onboarding(message.chat.id, tg_id)

    @bot.message_handler(func=lambda m: m.from_user.id in state.user_state and bool(m.text) and not m.text.startswith("/"))
    def handle_onboarding_input(message):
        tg_id = message.from_user.id
        current_state = state.user_state[tg_id]
        step = state.STEPS[current_state["step"]]
        text = message.text.strip()
        if step == "desired_role":
            if not text:
                bot.send_message(message.chat.id, "Введи должность текстом.")
                return
            current_state["profile"]["desired_role"] = text
            finish_step(message.chat.id, tg_id)
            return
        if step in ["work_format", "locations", "experience"]:
            if text.lower() != "далее":
                bot.send_message(message.chat.id, "Используй кнопки и нажми «Далее», когда будешь готов.")
                return
            finish_step(message.chat.id, tg_id)
            return
        if step == "min_salary":
            if text.lower() == "пропустить":
                current_state["profile"]["min_salary"] = None
                finish_step(message.chat.id, tg_id)
                return
            salary = parse_salary(text)
            if salary is None:
                bot.send_message(message.chat.id, "Нужно число. Попробуй ещё раз.")
                return
            current_state["profile"]["min_salary"] = salary
            finish_step(message.chat.id, tg_id)
            return
        if step in ["skills", "stop_words", "blacklisted_companies"]:
            if text.lower() == "пропустить":
                current_state["profile"][step] = []
            else:
                current_state["profile"][step] = parse_list(text)
                if step == "skills":
                    raw_count = len(current_state["profile"][step])
                    unique_count = len(normalize_skills_list(current_state["profile"][step]))
                    if raw_count:
                        message_text = f"Вы указали {raw_count} навыков."
                        if unique_count != raw_count:
                            message_text = f"Вы указали {raw_count} навыков (уникальных: {unique_count})."
                        bot.send_message(message.chat.id, message_text)
            finish_step(message.chat.id, tg_id)

    @bot.callback_query_handler(func=lambda c: c.data == "confirm_profile")
    def handle_profile_confirm(call):
        tg_id = call.from_user.id
        bot.answer_callback_query(call.id)
        current_state = state.user_state.get(tg_id)
        if not current_state:
            if tg_id in state.profiles:
                bot.send_message(call.message.chat.id, "Профиль уже сохранён.", reply_markup=build_main_menu())
                return
            bot.send_message(call.message.chat.id, "Сессия онбординга сброшена (бот перезапускался). Нажми /start и заполни профиль заново.")
            return
        persist_profile(tg_id, current_state["profile"], settings)
        state.user_state.pop(tg_id, None)
        bot.send_message(call.message.chat.id, "Профиль сохранён.", reply_markup=build_main_menu())

    @bot.callback_query_handler(func=lambda c: c.data == "edit_menu")
    def handle_edit_menu(call):
        bot.answer_callback_query(call.id)
        show_edit_menu(call.message.chat.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("edit:"))
    def handle_edit_section(call):
        action = call.data.split(":", 1)[1]
        bot.answer_callback_query(call.id)
        if action == "cancel":
            show_main_menu(call.message.chat.id)
            return
        start_editing(call.message.chat.id, call.from_user.id, action)

    @bot.callback_query_handler(func=lambda c: c.data == "profile_restart")
    def handle_profile_restart(call):
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "Ок, давай заполним профиль заново.", reply_markup=types.ReplyKeyboardRemove())
        start_onboarding(call.message.chat.id, call.from_user.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("wf:"))
    def handle_work_format_toggle(call):
        tg_id = call.from_user.id
        current_state = state.user_state.get(tg_id)
        if not current_state or state.STEPS[current_state["step"]] != "work_format":
            bot.answer_callback_query(call.id)
            return
        option = call.data.split(":", 1)[1].strip()
        selected = current_state["profile"].setdefault("work_formats", [])
        if option in selected:
            selected.remove(option)
        else:
            selected.append(option)
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=build_toggle_kb(state.WORK_FORMAT_OPTIONS, set(selected), "wf"))
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("loc:"))
    def handle_location_toggle(call):
        tg_id = call.from_user.id
        current_state = state.user_state.get(tg_id)
        if not current_state or state.STEPS[current_state["step"]] != "locations":
            bot.answer_callback_query(call.id)
            return
        option = call.data.split(":", 1)[1].strip()
        profile = current_state["profile"]
        if option == "Не важно":
            profile["locations_any"] = not profile.get("locations_any", False)
            if profile["locations_any"]:
                profile["locations"] = []
        else:
            if profile.get("locations_any"):
                profile["locations_any"] = False
            selected = profile.setdefault("locations", [])
            if option in selected:
                selected.remove(option)
            else:
                selected.append(option)
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=build_locations_kb(profile))
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("exp:"))
    def handle_experience_toggle(call):
        tg_id = call.from_user.id
        current_state = state.user_state.get(tg_id)
        if not current_state or state.STEPS[current_state["step"]] != "experience":
            bot.answer_callback_query(call.id)
            return
        option = call.data.split(":", 1)[1].strip()
        profile = current_state["profile"]
        profile["experience"] = None if profile.get("experience") == option else option
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=build_experience_kb(profile))
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("menu:"))
    def handle_menu_action(call):
        action = call.data.split(":", 1)[1]
        bot.answer_callback_query(call.id)
        if action == "resume":
            show_resume(call.message, call.from_user.id)
            return
        if action == "restart":
            bot.send_message(call.message.chat.id, "Ок, давай заполним профиль заново.")
            start_onboarding(call.message.chat.id, call.from_user.id)
            return
        if action == "vacancies":
            show_vacancies(call.message, call.from_user.id)

    @bot.callback_query_handler(func=lambda c: c.data == "vac:next")
    def handle_vacancy_next(call):
        bot.answer_callback_query(call.id)
        send_vacancy(call.message.chat.id, call.from_user.id)

    @bot.message_handler(commands=["menu"])
    def handle_menu(message):
        show_main_menu(message.chat.id)

    @bot.message_handler(commands=["resume"])
    def handle_resume_command(message):
        show_resume(message)

    @bot.message_handler(commands=["restart"])
    def handle_restart_command(message):
        bot.send_message(message.chat.id, "Ок, давай заполним профиль заново.")
        start_onboarding(message.chat.id, message.from_user.id)

    @bot.message_handler(commands=["vacancies"])
    def handle_vacancies_command(message):
        show_vacancies(message)

    @bot.message_handler(func=lambda m: m.text == "📄 Резюме")
    def handle_resume_button(message):
        show_resume(message)

    @bot.message_handler(func=lambda m: m.text == "📄 Моё резюме")
    def handle_resume_button_legacy(message):
        show_resume(message)

    @bot.message_handler(func=lambda m: m.text == "👀 Вакансии")
    def handle_vacancies_button(message):
        show_vacancies(message)

    @bot.message_handler(func=lambda m: m.text == "👀 Смотреть вакансии")
    def handle_vacancies_button_legacy(message):
        show_vacancies(message)
