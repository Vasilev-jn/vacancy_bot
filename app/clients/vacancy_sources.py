import logging

import requests

from app.config import Settings
from app.services.matching import build_query
from app.utils.text import clean_html

logger = logging.getLogger(__name__)
_direct_session = requests.Session()
_direct_session.trust_env = False


def safe_get_json(url: str, settings: Settings, params=None, headers=None):
    try:
        response = _direct_session.get(url, params=params, headers=headers, timeout=settings.request_timeout)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        logger.warning("Request failed for %s: %s", url, exc)
        return None


def map_work_format(value) -> str | None:
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


def normalize_hh(item: dict) -> dict:
    salary = item.get("salary") or item.get("salary_range") or {}
    snippet = item.get("snippet") or {}
    schedule = item.get("schedule") or {}
    work_format = item.get("work_format") or schedule
    if isinstance(work_format, list):
        work_format_value = ", ".join(str((entry or {}).get("name") or entry) for entry in work_format)
    elif isinstance(work_format, dict):
        work_format_value = work_format.get("name") or work_format.get("id")
    else:
        work_format_value = work_format

    experience = item.get("experience") or {}
    if isinstance(experience, dict):
        experience_value = experience.get("name") or experience.get("id")
    else:
        experience_value = experience

    return {
        "source": "hh",
        "source_name": "HH.ru",
        "source_vacancy_id": item.get("id"),
        "title": item.get("name"),
        "company_name": (item.get("employer") or {}).get("name"),
        "location": (item.get("area") or {}).get("name"),
        "work_format": map_work_format(work_format_value),
        "experience": experience_value,
        "salary_from": salary.get("from"),
        "salary_to": salary.get("to"),
        "currency": salary.get("currency"),
        "published_at": item.get("published_at"),
        "url": item.get("alternate_url") or item.get("url"),
        "description": clean_html(item.get("description") or snippet.get("responsibility") or snippet.get("requirement")),
    }


def build_hh_headers(settings: Settings) -> dict[str, str]:
    return {"User-Agent": settings.hh_user_agent}


def fetch_hh_details(vacancy_id: str, settings: Settings):
    if not vacancy_id:
        return None
    return safe_get_json(f"{settings.hh_base_url}/vacancies/{vacancy_id}", settings, headers=build_hh_headers(settings))


def fetch_hh_with_info(profile: dict, settings: Settings, limit: int | None = None) -> tuple[list[dict], dict]:
    effective_limit = max(limit or settings.per_source_cache, 1)
    page_count = max(settings.hh_page_range, 1)
    per_page = max(min((effective_limit + page_count - 1) // page_count, 100), 1)
    query = build_query(profile)
    params = {
        "per_page": per_page,
        "order_by": "publication_time",
    }
    if query:
        params["text"] = query
    min_salary = profile.get("min_salary")
    if min_salary:
        params["salary"] = min_salary
        params["only_with_salary"] = "true"

    vacancies = []
    last_error = None
    for page in range(page_count):
        params["page"] = page
        data = safe_get_json(f"{settings.hh_base_url}/vacancies", settings, params=params, headers=build_hh_headers(settings))
        if data is None:
            last_error = "request_failed"
            break
        items = data.get("items") or []
        vacancies.extend(normalize_hh(item) for item in items)
        if len(vacancies) >= effective_limit:
            vacancies = vacancies[:effective_limit]
            break
        if page + 1 >= int(data.get("pages") or 0):
            break

    info = {
        "source": "hh",
        "source_name": "HH.ru",
        "items": len(vacancies),
        "limit": effective_limit,
        "query": query,
        "url": f"{settings.hh_base_url}/vacancies",
    }
    if last_error:
        info["error"] = last_error
    return vacancies, info
