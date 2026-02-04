import copy
import html
import os
import random
import re
import time
import math
import hashlib

from dotenv import load_dotenv
import telebot
from telebot import types
import requests
try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None

load_dotenv()
token = os.getenv("BOT_TOKEN")
if not token:
    raise RuntimeError("BOT_TOKEN is missing in .env")

bot = telebot.TeleBot(token, parse_mode="HTML")

DEFAULT_PROFILE = {
    "desired_role": "",
    "work_formats": [],
    "locations": [],
    "locations_any": False,
    "min_salary": None,
    "experience": None,
    "skills": [],
    "stop_words": [],
    "blacklisted_companies": [],
}

WORK_FORMAT_OPTIONS = ["Удалёнка", "Гибрид", "Офис"]
LOCATION_OPTIONS = [
    "Москва",
    "Санкт-Петербург",
    "Новосибирск",
    "Екатеринбург",
    "Казань",
    "Нижний Новгород",
    "Самара",
    "Ростов-на-Дону",
    "Уфа",
    "Краснодар",
    "Воронеж",
    "Пермь",
    "Челябинск",
    "Омск",
    "Волгоград",
    "Владивосток",
    "Не важно",
]
EXPERIENCE_OPTIONS = ["Нет опыта", "1-3 года", "3-6 лет", "6+ лет"]

HH_BASE_URL = os.getenv("HH_BASE_URL", "https://api.hh.ru").rstrip("/")
HH_TOKEN = os.getenv("HH_TOKEN")
HH_USER_AGENT = os.getenv("HH_USER_AGENT", "VacancyBot/0.1")

REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "15"))
MAX_QUERY_SKILLS = 5
VACANCY_CACHE_SIZE = int(os.getenv("VACANCY_CACHE_SIZE", "15"))
PER_SOURCE_CACHE = int(os.getenv("PER_SOURCE_CACHE", str(VACANCY_CACHE_SIZE)))
FETCH_ATTEMPTS = int(os.getenv("FETCH_ATTEMPTS", "3"))
MAX_SEEN_PER_USER = int(os.getenv("MAX_SEEN_PER_USER", "500"))
MATCH_THRESHOLD = float(os.getenv("MATCH_THRESHOLD", "0.5"))
SKILLS_SAMPLE_RATIO = float(os.getenv("SKILLS_SAMPLE_RATIO", "0.5"))
VACANCY_CACHE_TTL = int(os.getenv("VACANCY_CACHE_TTL", "600"))
HH_PAGE_RANGE = max(int(os.getenv("HH_PAGE_RANGE", "4")), 0)
vacancy_cache = {}
seen_vacancies = {}
last_fetch_info = {}

PG_DSN = os.getenv("PG_DSN")
PG_ENABLED = bool(PG_DSN and psycopg2)

STEPS = [
    "desired_role",
    "work_format",
    "locations",
    "min_salary",
    "experience",
    "skills",
    "stop_words",
    "blacklisted_companies",
]

user_state = {}
profiles = {}


def parse_list(text: str):
    return [t.strip() for t in text.split(",") if t.strip()]


def parse_salary(text: str):
    cleaned = text.replace(" ", "").replace("_", "")
    try:
        return int(cleaned)
    except ValueError:
        return None


def format_value(value):
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) if value else "не указано"
    if value is None or value == "":
        return "не указано"
    return str(value)


def init_db():
    if not PG_ENABLED:
        return
    with psycopg2.connect(PG_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS profiles (
                    tg_id BIGINT PRIMARY KEY,
                    profile JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )


def save_profile_db(tg_id, profile):
    if not PG_ENABLED:
        return False
    with psycopg2.connect(PG_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO profiles (tg_id, profile, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (tg_id)
                DO UPDATE SET profile = EXCLUDED.profile, updated_at = NOW();
                """,
                (tg_id, psycopg2.extras.Json(profile)),
            )
    return True


def load_profile_db(tg_id):
    if not PG_ENABLED:
        return None
    with psycopg2.connect(PG_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT profile FROM profiles WHERE tg_id = %s;", (tg_id,))
            row = cur.fetchone()
            if not row:
                return None
            return row[0]


def escape_text(value):
    if value is None:
        return ""
    return html.escape(str(value))


def clean_html(text):
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>\s*<p>", "\n\n", text)
    text = re.sub(r"(?i)</p>", "\n\n", text)
    text = re.sub(r"(?i)<p[^>]*>", "", text)
    text = re.sub(r"(?i)<li[^>]*>", "- ", text)
    text = re.sub(r"(?i)</li>", "\n", text)
    text = re.sub(r"(?i)</ul>|</ol>", "\n", text)
    text = re.sub(r"(?i)<ul[^>]*>|<ol[^>]*>", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def limit_text(text, limit=3800):
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"

def build_query(profile):
    role = (profile.get("desired_role") or "").strip()
    if role:
        return role
    return "вакансия"


def safe_get_json(url, params=None, headers=None):
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        print(f"Request failed: {url} -> {exc}")
        return None


def format_salary(salary_from=None, salary_to=None, currency=None):
    if salary_from is None and salary_to is None:
        return "не указана"
    if salary_from and salary_to:
        return f"{salary_from}–{salary_to} {currency or ''}".strip()
    if salary_from:
        return f"от {salary_from} {currency or ''}".strip()
    return f"до {salary_to} {currency or ''}".strip()


def map_work_format(value):
    if not value:
        return None
    text = str(value).lower()
    if "удал" in text or "remote" in text:
        return "Удалёнка"
    if "гибрид" in text or "hybrid" in text:
        return "Гибрид"
    if "офис" in text or "full" in text or "полный день" in text:
        return "Офис"
    return str(value)


def normalize_hh(item):
    salary = item.get("salary") or {}
    snippet = item.get("snippet") or {}
    schedule = item.get("schedule") or {}
    experience = item.get("experience") or {}
    if isinstance(experience, dict):
        experience_value = experience.get("name") or experience.get("id")
    else:
        experience_value = experience
    work_format = map_work_format(schedule.get("name") or schedule.get("id"))
    description = item.get("description") or snippet.get("responsibility") or snippet.get("requirement")
    description = clean_html(description)
    return {
        "source": "hh",
        "source_vacancy_id": item.get("id"),
        "title": item.get("name"),
        "company_name": (item.get("employer") or {}).get("name"),
        "location": (item.get("area") or {}).get("name"),
        "work_format": work_format,
        "experience": experience_value,
        "salary_from": salary.get("from"),
        "salary_to": salary.get("to"),
        "currency": salary.get("currency"),
        "published_at": item.get("published_at"),
        "url": item.get("alternate_url") or item.get("url"),
        "description": description,
    }


def fetch_hh_details(vacancy_id, headers):
    if not vacancy_id:
        return None
    return safe_get_json(f"{HH_BASE_URL}/vacancies/{vacancy_id}", headers=headers)


def build_hh_headers():
    headers = {"User-Agent": HH_USER_AGENT}
    if HH_TOKEN:
        headers["Authorization"] = f"Bearer {HH_TOKEN}"
    return headers


def fetch_hh(profile, limit=PER_SOURCE_CACHE, tg_id=None):
    query = build_query(profile)
    headers = build_hh_headers()
    page = random.randint(0, HH_PAGE_RANGE) if HH_PAGE_RANGE > 0 else 0

    def do_request(page_num):
        params = {"text": query, "per_page": limit, "page": page_num}
        data = safe_get_json(f"{HH_BASE_URL}/vacancies", params=params, headers=headers)
        items = data.get("items", []) if data else []
        info = {
            "source": "hh",
            "query": query,
            "page": page_num,
            "per_page": limit,
            "items": len(items),
        }
        if data is None:
            info["error"] = "request_failed"
        else:
            info["found"] = data.get("found")
        return items, info

    items, info = do_request(page)
    if not items and page != 0:
        items, info = do_request(0)

    if tg_id is not None:
        last_fetch_info[tg_id] = info

    items = items[:limit]
    normalized = [normalize_hh(item) for item in items]
    return normalized


def enrich_hh_vacancy(profile, vacancy):
    vacancy_id = vacancy.get("source_vacancy_id")
    if not vacancy_id:
        matched, raw_total, unique_total, ratio = compute_match_stats(profile, vacancy)
        if raw_total > 0:
            vacancy["match_count"] = matched
            vacancy["match_total"] = raw_total
            vacancy["match_unique_total"] = unique_total
            vacancy["match_ratio"] = ratio
        return vacancy
    details = fetch_hh_details(vacancy_id, build_hh_headers())
    if not details:
        matched, raw_total, unique_total, ratio = compute_match_stats(profile, vacancy)
        if raw_total > 0:
            vacancy["match_count"] = matched
            vacancy["match_total"] = raw_total
            vacancy["match_unique_total"] = unique_total
            vacancy["match_ratio"] = ratio
        return vacancy
    enriched = normalize_hh(details)
    matched, raw_total, unique_total, ratio = compute_match_stats(profile, enriched)
    if raw_total > 0:
        enriched["match_count"] = matched
        enriched["match_total"] = raw_total
        enriched["match_unique_total"] = unique_total
        enriched["match_ratio"] = ratio
    elif "match_ratio" in vacancy:
        enriched["match_ratio"] = vacancy["match_ratio"]
    return enriched


def normalize_match_text(vacancy):
    title = vacancy.get("title") or ""
    description = vacancy.get("description") or vacancy.get("description_snippet") or ""
    text = f"{title}\n{description}"
    text = clean_html(text).lower()
    return text


def extract_tokens(text):
    return set(re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9+#]+", text.lower()))


def normalize_skills_list(skills):
    result = []
    seen = set()
    for skill in skills:
        value = str(skill).strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def sample_skills(skills, ratio, seed):
    if not skills:
        return []
    ratio = max(0.0, min(1.0, ratio))
    skills = normalize_skills_list(skills)
    if not skills:
        return []
    limit = int(math.ceil(len(skills) * ratio))
    limit = max(1, min(len(skills), limit))
    if limit >= len(skills):
        return skills
    seed_value = str(seed or "")
    def sort_key(skill):
        payload = f"{seed_value}|{skill.lower()}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()
    ordered = sorted(skills, key=sort_key)
    return ordered[:limit]


def skill_in_text(skill, text, tokens):
    value = str(skill).strip().lower()
    if not value:
        return False
    if " " in value:
        return value in text
    if any(ch in value for ch in ".-/:"):
        if value in text:
            return True
        parts = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9+#]+", value)
        return bool(parts) and all(part in tokens for part in parts)
    return value in tokens


def skill_match_ratio(skills, text, tokens):
    total = 0
    matched = 0
    for skill in skills:
        value = str(skill).strip()
        if not value:
            continue
        total += 1
        if skill_in_text(value, text, tokens):
            matched += 1
    if total == 0:
        return 0.0
    return matched / total


def role_match(text, tokens, role):
    role_value = (role or "").strip().lower()
    if not role_value:
        return True
    if role_value in text:
        return True
    words = [w for w in re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]+", role_value) if len(w) >= 2]
    if not words:
        return False
    return any(word in tokens for word in words)


def compute_match_stats(profile, vacancy):
    raw_skills = profile.get("skills") or []
    if not isinstance(raw_skills, list):
        raw_skills = [raw_skills]
    raw_skills = [str(skill).strip() for skill in raw_skills if str(skill).strip()]
    raw_total = len(raw_skills)
    unique_skills = normalize_skills_list(raw_skills)
    unique_total = len(unique_skills)
    if unique_total == 0:
        return 0, raw_total, 0, 0.0
    text = normalize_match_text(vacancy)
    tokens = extract_tokens(text)
    matched = 0
    for skill in unique_skills:
        if skill_in_text(skill, text, tokens):
            matched += 1
    ratio = matched / unique_total if unique_total else 0.0
    return matched, raw_total, unique_total, ratio


def compute_match_ratio(profile, vacancy):
    skills = profile.get("skills") or []
    if not isinstance(skills, list):
        skills = [skills]
    role = profile.get("desired_role") or ""
    text = normalize_match_text(vacancy)
    tokens = extract_tokens(text)
    if skills:
        seed = vacancy.get("source_vacancy_id") or vacancy.get("url") or vacancy.get("title") or ""
        sampled = sample_skills(skills, SKILLS_SAMPLE_RATIO, seed)
        return skill_match_ratio(sampled, text, tokens)
    return 1.0 if role_match(text, tokens, role) else 0.0


def filter_vacancies_by_profile(profile, vacancies):
    skills = profile.get("skills") or []
    if not isinstance(skills, list):
        skills = [skills]
    filtered = []
    for vacancy in vacancies:
        if skills:
            ratio = compute_match_ratio(profile, vacancy)
            if ratio < MATCH_THRESHOLD:
                continue
            vacancy["match_ratio"] = ratio
        else:
            ratio = compute_match_ratio(profile, vacancy)
            if ratio <= 0.0:
                continue
            vacancy["match_ratio"] = 1.0
        filtered.append(vacancy)
    return filtered


def fetch_vacancies(profile, tg_id=None):
    vacancies = fetch_hh(profile, limit=PER_SOURCE_CACHE, tg_id=tg_id)
    return vacancies


def vacancy_key(vacancy):
    source = vacancy.get("source") or ""
    source_id = vacancy.get("source_vacancy_id")
    if source and source_id:
        return f"{source}:{source_id}"
    url = vacancy.get("url")
    if url:
        return f"url:{url}"
    title = vacancy.get("title") or ""
    company = vacancy.get("company_name") or ""
    location = vacancy.get("location") or ""
    if not (title or company or location):
        return None
    return f"fallback:{source}:{title}:{company}:{location}".lower()


def filter_new_vacancies(tg_id, vacancies):
    user_seen = seen_vacancies.get(tg_id, set())
    batch_seen = set()
    result = []
    for vacancy in vacancies:
        key = vacancy_key(vacancy)
        if key:
            if key in user_seen or key in batch_seen:
                continue
            batch_seen.add(key)
        result.append(vacancy)
    return result


def mark_vacancy_seen(tg_id, vacancy):
    key = vacancy_key(vacancy)
    if not key:
        return
    user_seen = seen_vacancies.setdefault(tg_id, set())
    user_seen.add(key)
    while len(user_seen) > MAX_SEEN_PER_USER:
        user_seen.pop()


def build_vacancy_text(vacancy):
    title = escape_text(vacancy.get("title") or "Без названия")
    company = escape_text(vacancy.get("company_name") or "Компания не указана")
    location = escape_text(vacancy.get("location") or "Локация не указана")
    work_format = escape_text(vacancy.get("work_format") or "не указан")
    experience = escape_text(vacancy.get("experience") or "не указан")
    salary = format_salary(vacancy.get("salary_from"), vacancy.get("salary_to"), vacancy.get("currency"))
    description = vacancy.get("description") or vacancy.get("description_snippet") or ""
    description = limit_text(clean_html(description))
    source = vacancy.get("source") or "source"
    match_count = vacancy.get("match_count")
    match_total = vacancy.get("match_total")
    match_unique_total = vacancy.get("match_unique_total")
    match_text = ""
    if isinstance(match_count, int) and isinstance(match_total, int) and match_total > 0:
        match_text = f"\nСовпадения навыков: {match_count} из {match_total}"
        if isinstance(match_unique_total, int) and match_unique_total > 0 and match_unique_total != match_total:
            match_text += f" (уникальных {match_unique_total})"

    text = (
        f"<b>{title}</b>\n"
        f"{company}\n"
        f"{location}\n"
        f"Формат: {work_format}\n"
        f"Опыт: {experience}\n"
        f"Зарплата: {salary}\n"
        f"Источник: {source}{match_text}"
    )
    if description:
        text += f"\n\n{escape_text(description)}"
    return text


def build_vacancy_kb(vacancy):
    url = vacancy.get("url")
    kb = types.InlineKeyboardMarkup()
    row = []
    if url:
        row.append(types.InlineKeyboardButton("Открыть", url=url))
    row.append(types.InlineKeyboardButton("Следующая ➡️", callback_data="vac:next"))
    if row:
        kb.row(*row)
    return kb


def format_fetch_info(info):
    if not info:
        return None
    if info.get("error"):
        return "HH сейчас не отвечает. Попробуй позже."
    if info.get("items", 0) == 0:
        query = info.get("query")
        if query:
            return f"HH не вернул вакансий по запросу: {query}"
        return "HH не вернул вакансий по текущему запросу."
    return None


def build_reply_kb(options):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for opt in options:
        kb.add(types.KeyboardButton(str(opt)))
    return kb


def build_toggle_kb(options, selected_set, prefix):
    kb = types.InlineKeyboardMarkup()
    row = []
    for option in options:
        label = f"✅ {option}" if option in selected_set else option
        row.append(types.InlineKeyboardButton(label, callback_data=f"{prefix}:{option}"))
        if len(row) == 2:
            kb.row(*row)
            row = []
    if row:
        kb.row(*row)
    return kb


def build_locations_kb(profile):
    selected = set(profile.get("locations") or [])
    any_selected = bool(profile.get("locations_any"))
    kb = types.InlineKeyboardMarkup()
    row = []
    for option in LOCATION_OPTIONS:
        is_selected = any_selected if option == "Не важно" else option in selected
        label = f"✅ {option}" if is_selected else option
        row.append(types.InlineKeyboardButton(label, callback_data=f"loc:{option}"))
        if len(row) == 2:
            kb.row(*row)
            row = []
    if row:
        kb.row(*row)
    return kb


def build_experience_kb(profile):
    selected = profile.get("experience")
    kb = types.InlineKeyboardMarkup()
    row = []
    for option in EXPERIENCE_OPTIONS:
        label = f"✅ {option}" if option == selected else option
        row.append(types.InlineKeyboardButton(label, callback_data=f"exp:{option}"))
        if len(row) == 2:
            kb.row(*row)
            row = []
    if row:
        kb.row(*row)
    return kb


def start_onboarding(chat_id, tg_id):
    profile = copy.deepcopy(DEFAULT_PROFILE)
    user_state[tg_id] = {"step": 0, "profile": profile, "mode": "onboarding"}
    ask_next_step(chat_id, tg_id)


def start_editing(chat_id, tg_id, step_key):
    profile = profiles.get(tg_id)
    if not profile and PG_ENABLED:
        profile = load_profile_db(tg_id)
        if profile:
            profiles[tg_id] = profile
    if not profile:
        bot.send_message(chat_id, "Профиль ещё не заполнен. Нажми /start.")
        return
    if step_key not in STEPS:
        bot.send_message(chat_id, "Неизвестный раздел.")
        return
    user_state[tg_id] = {"step": STEPS.index(step_key), "profile": profile, "mode": "edit"}
    ask_next_step(chat_id, tg_id)


def ask_next_step(chat_id, tg_id):
    state = user_state[tg_id]
    step = STEPS[state["step"]]
    profile = state["profile"]

    if step == "desired_role":
        bot.send_message(chat_id, "Введи желаемую должность:", reply_markup=types.ReplyKeyboardRemove())
        return
    if step == "work_format":
        kb = build_toggle_kb(WORK_FORMAT_OPTIONS, set(profile.get("work_formats") or []), "wf")
        bot.send_message(chat_id, "Выбери формат работы (можно несколько):", reply_markup=kb)
        bot.send_message(chat_id, "Когда готов — нажми «Далее».", reply_markup=build_reply_kb(["Далее"]))
        return
    if step == "locations":
        kb = build_locations_kb(profile)
        bot.send_message(chat_id, "Выбери локации (можно несколько) или «Не важно».", reply_markup=kb)
        bot.send_message(chat_id, "Когда готов — нажми «Далее».", reply_markup=build_reply_kb(["Далее"]))
        return
    if step == "min_salary":
        bot.send_message(
            chat_id,
            "Минимальная зарплата? (число). Можно пропустить.",
            reply_markup=build_reply_kb(["Пропустить"]),
        )
        return
    if step == "experience":
        kb = build_experience_kb(profile)
        bot.send_message(chat_id, "Выбери опыт (только один):", reply_markup=kb)
        bot.send_message(chat_id, "Когда готов — нажми «Далее».", reply_markup=build_reply_kb(["Далее"]))
        return
    if step == "skills":
        bot.send_message(
            chat_id,
            "Навыки (ключевые слова через запятую). Можно пропустить.",
            reply_markup=build_reply_kb(["Пропустить"]),
        )
        return
    if step == "stop_words":
        bot.send_message(
            chat_id,
            "Стоп-слова через запятую. Можно пропустить.",
            reply_markup=build_reply_kb(["Пропустить"]),
        )
        return
    if step == "blacklisted_companies":
        bot.send_message(
            chat_id,
            "Чёрный список компаний через запятую. Можно пропустить.",
            reply_markup=build_reply_kb(["Пропустить"]),
        )
        return


def finish_step(chat_id, tg_id):
    state = user_state[tg_id]
    profile = state["profile"]
    if state.get("mode") == "edit":
        profiles[tg_id] = profile
        save_profile_db(tg_id, profile)
        vacancy_cache.pop(tg_id, None)
        seen_vacancies.pop(tg_id, None)
        user_state.pop(tg_id, None)
        send_profile_text(chat_id, profile, with_edit=True, with_restart=True)
        bot.send_message(chat_id, "Профиль обновлён.", reply_markup=build_main_menu())
        return

    state["step"] += 1
    if state["step"] >= len(STEPS):
        send_profile_summary(chat_id, tg_id)
    else:
        ask_next_step(chat_id, tg_id)


def send_profile_summary(chat_id, tg_id):
    profile = user_state[tg_id]["profile"]
    bot.send_message(chat_id, "Проверь профиль:", reply_markup=types.ReplyKeyboardRemove())
    send_profile_text(chat_id, profile, with_confirm=True, with_edit=True, with_restart=True)


def format_profile_text(profile):
    role = profile.get("desired_role") or "не указана"
    work_formats = format_value(profile.get("work_formats"))
    if profile.get("locations_any"):
        locations = "не важно"
    else:
        locations = format_value(profile.get("locations"))
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
        f"Мин. зарплата: {min_salary}\n"
        f"Опыт: {experience}\n"
        f"\nНавыки: {skills}\n"
        f"\n"
        f"Стоп-слова: {stop_words}\n"
        f"Чёрный список: {companies}"
    )


def send_profile_text(chat_id, profile, with_confirm=False, with_edit=False, with_restart=False):
    text = format_profile_text(profile)
    kb = None
    if with_confirm or with_edit or with_restart:
        kb = types.InlineKeyboardMarkup()
        row = []
        if with_confirm:
            row.append(types.InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_profile"))
        if with_edit:
            row.append(types.InlineKeyboardButton("✏️ Изменить", callback_data="edit_menu"))
        if with_restart:
            row.append(types.InlineKeyboardButton("🔁 Заново", callback_data="profile_restart"))
        if row:
            kb.row(*row)
    bot.send_message(chat_id, text, reply_markup=kb)


def build_main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.row(
        types.KeyboardButton("📄 Резюме"),
        types.KeyboardButton("👀 Вакансии"),
    )
    return kb


def show_main_menu(chat_id):
    bot.send_message(chat_id, "Ок.", reply_markup=build_main_menu())


def build_edit_menu():
    kb = types.InlineKeyboardMarkup()
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
            kb.row(*row)
            row = []
    if row:
        kb.row(*row)
    kb.row(types.InlineKeyboardButton("⬅️ Назад", callback_data="edit:cancel"))
    return kb


def show_edit_menu(chat_id):
    bot.send_message(chat_id, "Что изменить?", reply_markup=build_edit_menu())
@bot.message_handler(commands=["start"])
def handle_start(message):
    tg_id = message.from_user.id
    profile = get_profile_for_user(tg_id)
    if profile:
        bot.reply_to(message, "Привет! Я тебя помню — вот твой профиль:", reply_markup=build_main_menu())
        send_profile_text(message.chat.id, profile, with_edit=True, with_restart=True)
        return
    bot.reply_to(message, "Привет! Давай настроим профиль.")
    start_onboarding(message.chat.id, tg_id)


@bot.message_handler(func=lambda m: m.from_user.id in user_state and not m.text.startswith("/"))
def handle_onboarding_input(message):
    tg_id = message.from_user.id
    state = user_state[tg_id]
    step = STEPS[state["step"]]
    text = message.text.strip()

    if step == "desired_role":
        if not text:
            bot.send_message(message.chat.id, "Введи должность текстом.")
            return
        state["profile"]["desired_role"] = text
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
            state["profile"]["min_salary"] = None
            finish_step(message.chat.id, tg_id)
            return
        salary = parse_salary(text)
        if salary is None:
            bot.send_message(message.chat.id, "Нужно число. Попробуй ещё раз.")
            return
        state["profile"]["min_salary"] = salary
        finish_step(message.chat.id, tg_id)
        return

    if step in ["skills", "stop_words", "blacklisted_companies"]:
        if text.lower() == "пропустить":
            state["profile"][step] = []
        else:
            state["profile"][step] = parse_list(text)
            if step == "skills":
                raw_count = len(state["profile"][step])
                unique_count = len(normalize_skills_list(state["profile"][step]))
                if raw_count:
                    if unique_count != raw_count:
                        bot.send_message(
                            message.chat.id,
                            f"Вы указали {raw_count} навыков (уникальных: {unique_count})."
                        )
                    else:
                        bot.send_message(message.chat.id, f"Вы указали {raw_count} навыков.")
        finish_step(message.chat.id, tg_id)
        return


@bot.callback_query_handler(func=lambda c: c.data == "confirm_profile")
def handle_profile_confirm(call):
    tg_id = call.from_user.id
    bot.answer_callback_query(call.id)
    state = user_state.get(tg_id)
    if not state:
        if tg_id in profiles:
            bot.send_message(call.message.chat.id, "Профиль уже сохранён.", reply_markup=build_main_menu())
            return
        bot.send_message(
            call.message.chat.id,
            "Сессия онбординга сброшена (бот перезапускался). Нажми /start и заполни профиль заново."
        )
        return
    profiles[tg_id] = state["profile"]
    save_profile_db(tg_id, profiles[tg_id])
    vacancy_cache.pop(tg_id, None)
    seen_vacancies.pop(tg_id, None)
    user_state.pop(tg_id, None)
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
    state = user_state.get(tg_id)
    if not state or STEPS[state["step"]] != "work_format":
        bot.answer_callback_query(call.id)
        return
    option = call.data.split(":", 1)[1].strip()
    selected = state["profile"].setdefault("work_formats", [])
    if option in selected:
        selected.remove(option)
    else:
        selected.append(option)
    kb = build_toggle_kb(WORK_FORMAT_OPTIONS, set(selected), "wf")
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=kb)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("loc:"))
def handle_location_toggle(call):
    tg_id = call.from_user.id
    state = user_state.get(tg_id)
    if not state or STEPS[state["step"]] != "locations":
        bot.answer_callback_query(call.id)
        return
    option = call.data.split(":", 1)[1].strip()
    profile = state["profile"]
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
    kb = build_locations_kb(profile)
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=kb)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("exp:"))
def handle_experience_toggle(call):
    tg_id = call.from_user.id
    state = user_state.get(tg_id)
    if not state or STEPS[state["step"]] != "experience":
        bot.answer_callback_query(call.id)
        return
    option = call.data.split(":", 1)[1].strip()
    profile = state["profile"]
    if profile.get("experience") == option:
        profile["experience"] = None
    else:
        profile["experience"] = option
    kb = build_experience_kb(profile)
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=kb)
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
        show_vacancies_stub(call.message, call.from_user.id)
        return


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
    show_vacancies_stub(message)


@bot.message_handler(func=lambda m: m.text == "📄 Резюме")
def handle_resume_button(message):
    show_resume(message)


@bot.message_handler(func=lambda m: m.text == "📄 Моё резюме")
def handle_resume_button_legacy(message):
    show_resume(message)


@bot.message_handler(func=lambda m: m.text == "👀 Вакансии")
def handle_vacancies_button(message):
    show_vacancies_stub(message)


@bot.message_handler(func=lambda m: m.text == "👀 Смотреть вакансии")
def handle_vacancies_button_legacy(message):
    show_vacancies_stub(message)


def show_resume(message, user_id=None):
    uid = user_id if user_id is not None else message.from_user.id
    profile = profiles.get(uid)
    if not profile and PG_ENABLED:
        profile = load_profile_db(uid)
        if profile:
            profiles[uid] = profile
    if not profile:
        bot.send_message(message.chat.id, "Профиль ещё не заполнен. Нажми /start.")
        return
    send_profile_text(message.chat.id, profile, with_edit=True, with_restart=True)


def get_profile_for_user(tg_id):
    profile = profiles.get(tg_id)
    if not profile and PG_ENABLED:
        profile = load_profile_db(tg_id)
        if profile:
            profiles[tg_id] = profile
    return profile


def get_next_vacancy(tg_id):
    cache_entry = vacancy_cache.get(tg_id)
    cache_items = cache_entry.get("items", []) if cache_entry else []
    cache_age = None
    if cache_entry:
        cache_age = time.time() - cache_entry.get("ts", 0)
    if cache_items and cache_age is not None and cache_age < VACANCY_CACHE_TTL:
        idx = random.randrange(len(cache_items))
        vacancy = cache_items.pop(idx)
        vacancy_cache[tg_id] = {"ts": cache_entry.get("ts", time.time()), "items": cache_items}
        return vacancy

    profile = get_profile_for_user(tg_id)
    if not profile:
        return None

    for _ in range(FETCH_ATTEMPTS):
        vacancies = fetch_vacancies(profile, tg_id=tg_id)
        vacancies = filter_new_vacancies(tg_id, vacancies)
        if vacancies:
            vacancy_cache[tg_id] = {"ts": time.time(), "items": vacancies}
            idx = random.randrange(len(vacancy_cache[tg_id]["items"]))
            vacancy = vacancy_cache[tg_id]["items"].pop(idx)
            return vacancy

    vacancy_cache[tg_id] = {"ts": time.time(), "items": []}
    return None


def send_vacancy(chat_id, tg_id):
    vacancy = get_next_vacancy(tg_id)
    if not vacancy:
        info = format_fetch_info(last_fetch_info.get(tg_id))
        message = info or "Пока вакансий нет. Попробуй позже."
        bot.send_message(chat_id, message, reply_markup=build_main_menu())
        return
    profile = get_profile_for_user(tg_id)
    if profile and vacancy.get("source") == "hh":
        vacancy = enrich_hh_vacancy(profile, vacancy)
    mark_vacancy_seen(tg_id, vacancy)
    text = build_vacancy_text(vacancy)
    kb = build_vacancy_kb(vacancy)
    bot.send_message(chat_id, text, reply_markup=kb)


def show_vacancies_stub(message, user_id=None):
    uid = user_id if user_id is not None else message.from_user.id
    profile = get_profile_for_user(uid)
    if not profile:
        bot.send_message(message.chat.id, "Сначала заполни профиль: /start.")
        return
    send_vacancy(message.chat.id, uid)


init_db()


if __name__ == "__main__":
    print("Bot started...")
    bot.infinity_polling(skip_pending=True)
