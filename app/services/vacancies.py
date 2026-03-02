import random
import time

from app import state
from app.clients.vacancy_sources import fetch_fl_with_info, fetch_freelance_ru_with_info, fetch_hh_details, normalize_hh
from app.config import Settings
from app.services.matching import compute_match_stats, filter_vacancies_by_profile
from app.services.profile_store import get_profile_for_user
from app.utils.text import clean_html, escape_text, format_published_at_display, format_salary, limit_text


def enrich_hh_vacancy(profile: dict, vacancy: dict, settings: Settings) -> dict:
    vacancy_id = vacancy.get("source_vacancy_id")
    if not vacancy_id:
        matched, raw_total, unique_total, ratio = compute_match_stats(profile, vacancy)
        if raw_total > 0:
            vacancy["match_count"] = matched
            vacancy["match_total"] = raw_total
            vacancy["match_unique_total"] = unique_total
            vacancy["match_ratio"] = ratio
        return vacancy

    details = fetch_hh_details(vacancy_id, settings)
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


def fetch_vacancies(profile: dict, settings: Settings, tg_id: int | None = None) -> list[dict]:
    all_vacancies = []
    source_infos = []

    if settings.enable_fl_source:
        items, info = fetch_fl_with_info(profile, settings, limit=settings.per_source_cache)
        all_vacancies.extend(items)
        source_infos.append(info)

    if settings.enable_freelance_ru_source:
        items, info = fetch_freelance_ru_with_info(profile, settings, limit=settings.per_source_cache)
        all_vacancies.extend(items)
        source_infos.append(info)

    filtered = filter_vacancies_by_profile(profile, all_vacancies, settings)
    if tg_id is not None:
        state.last_fetch_info[tg_id] = {
            "source": "multi",
            "items": len(all_vacancies),
            "matched": len(filtered),
            "sources": source_infos,
        }
    return filtered


def vacancy_key(vacancy: dict) -> str | None:
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


def filter_new_vacancies(tg_id: int, vacancies: list[dict]) -> list[dict]:
    user_seen = state.seen_vacancies.get(tg_id, set())
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


def mark_vacancy_seen(tg_id: int, vacancy: dict, settings: Settings) -> None:
    key = vacancy_key(vacancy)
    if not key:
        return
    user_seen = state.seen_vacancies.setdefault(tg_id, set())
    user_seen.add(key)
    while len(user_seen) > settings.max_seen_per_user:
        user_seen.pop()


def build_vacancy_text(vacancy: dict) -> str:
    source = vacancy.get("source") or "source"
    if source in {"fl", "freelance_ru"}:
        title = escape_text(vacancy.get("title") or "Без названия")
        category = escape_text(vacancy.get("category") or "не указана")
        salary = format_salary(vacancy.get("salary_from"), vacancy.get("salary_to"), vacancy.get("currency"))
        if salary == "не указана" and vacancy.get("price_text"):
            salary = escape_text(vacancy.get("price_text"))
        published_at = escape_text(format_published_at_display(vacancy.get("published_at")))
        description = limit_text(clean_html(vacancy.get("description") or ""))
        source_name = escape_text(vacancy.get("source_name") or "FL.ru")
        company = escape_text(vacancy.get("company_name") or "")
        match_ratio = vacancy.get("match_ratio")
        match_text = ""
        if isinstance(match_ratio, (int, float)):
            match_text = f"\nСовпадение по ключам: {int(round(match_ratio * 100))}%"
        text = (
            f"<b>{title}</b>\n"
            f"Биржа: {source_name}\n"
            f"Категория: {category}\n"
            f"Бюджет: {salary}\n"
            f"Создан/опубликован: {published_at}{match_text}"
        )
        if company:
            text += f"\nЗаказчик: {company}"
        if description:
            text += f"\n\n{escape_text(description)}"
        return text

    title = escape_text(vacancy.get("title") or "Без названия")
    company = escape_text(vacancy.get("company_name") or "Компания не указана")
    location = escape_text(vacancy.get("location") or "Локация не указана")
    work_format = escape_text(vacancy.get("work_format") or "не указан")
    experience = escape_text(vacancy.get("experience") or "не указан")
    salary = format_salary(vacancy.get("salary_from"), vacancy.get("salary_to"), vacancy.get("currency"))
    description = limit_text(clean_html(vacancy.get("description") or vacancy.get("description_snippet") or ""))
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


def format_fetch_info(info: dict | None) -> str | None:
    if not info:
        return None
    if info.get("source") == "multi":
        sources = info.get("sources") or []
        total_items = info.get("items", 0)
        matched = info.get("matched")
        if sources and all(src.get("error") for src in sources):
            names = ", ".join(src.get("source_name") or src.get("source") or "source" for src in sources)
            return f"Источники сейчас недоступны ({names}). Попробуй позже."
        if matched == 0 and total_items > 0:
            return "Биржи вернули заказы, но по текущему фильтру ничего не подошло."
        if total_items == 0:
            return "Биржи не вернули заказов по текущему запросу."
        return None
    if info.get("source") == "fl":
        if info.get("error"):
            return "FL.ru сейчас не отвечает или вернул некорректный RSS. Попробуй позже."
        if info.get("items", 0) == 0:
            return "FL.ru не вернул подходящих заказов по текущему фильтру."
        return None
    if info.get("source") == "freelance_ru":
        if info.get("error"):
            return "Freelance.ru сейчас не отвечает. Попробуй позже."
        if info.get("items", 0) == 0:
            query = info.get("query") or "текущий запрос"
            return f"Freelance.ru не вернул заказов по запросу: {query}"
        return None
    if info.get("error"):
        return "HH сейчас не отвечает. Попробуй позже."
    if info.get("items", 0) == 0:
        query = info.get("query")
        if query:
            return f"HH не вернул вакансий по запросу: {query}"
        return "HH не вернул вакансий по текущему запросу."
    return None


def get_next_vacancy(tg_id: int, settings: Settings):
    cache_entry = state.vacancy_cache.get(tg_id)
    cache_items = cache_entry.get("items", []) if cache_entry else []
    cache_age = None
    if cache_entry:
        cache_age = time.time() - cache_entry.get("ts", 0)
    if cache_items and cache_age is not None and cache_age < settings.vacancy_cache_ttl:
        index = random.randrange(len(cache_items))
        vacancy = cache_items.pop(index)
        state.vacancy_cache[tg_id] = {"ts": cache_entry.get("ts", time.time()), "items": cache_items}
        return vacancy

    profile = get_profile_for_user(tg_id, settings)
    if not profile:
        return None

    for _ in range(settings.fetch_attempts):
        vacancies = fetch_vacancies(profile, settings, tg_id=tg_id)
        vacancies = filter_new_vacancies(tg_id, vacancies)
        if vacancies:
            state.vacancy_cache[tg_id] = {"ts": time.time(), "items": vacancies}
            index = random.randrange(len(state.vacancy_cache[tg_id]["items"]))
            return state.vacancy_cache[tg_id]["items"].pop(index)

    state.vacancy_cache[tg_id] = {"ts": time.time(), "items": []}
    return None
