import html
import logging
import random
import re
import xml.etree.ElementTree as ET

import requests

from app.config import Settings
from app.services.matching import build_query
from app.utils.text import clean_html

logger = logging.getLogger(__name__)


def safe_get_json(url: str, settings: Settings, params=None, headers=None):
    try:
        response = requests.get(url, params=params, headers=headers, timeout=settings.request_timeout)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        logger.warning("Request failed for %s: %s", url, exc)
        return None


def safe_get_text(url: str, settings: Settings, params=None, headers=None) -> str | None:
    try:
        response = requests.get(url, params=params, headers=headers, timeout=settings.request_timeout)
        response.raise_for_status()
        return response.text
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
    salary = item.get("salary") or {}
    snippet = item.get("snippet") or {}
    schedule = item.get("schedule") or {}
    experience = item.get("experience") or {}
    if isinstance(experience, dict):
        experience_value = experience.get("name") or experience.get("id")
    else:
        experience_value = experience
    return {
        "source": "hh",
        "source_vacancy_id": item.get("id"),
        "title": item.get("name"),
        "company_name": (item.get("employer") or {}).get("name"),
        "location": (item.get("area") or {}).get("name"),
        "work_format": map_work_format(schedule.get("name") or schedule.get("id")),
        "experience": experience_value,
        "salary_from": salary.get("from"),
        "salary_to": salary.get("to"),
        "currency": salary.get("currency"),
        "published_at": item.get("published_at"),
        "url": item.get("alternate_url") or item.get("url"),
        "description": clean_html(item.get("description") or snippet.get("responsibility") or snippet.get("requirement")),
    }


def build_hh_headers(settings: Settings) -> dict[str, str]:
    headers = {"User-Agent": settings.hh_user_agent}
    if settings.hh_token:
        headers["Authorization"] = f"Bearer {settings.hh_token}"
    return headers


def fetch_hh_details(vacancy_id: str, settings: Settings):
    if not vacancy_id:
        return None
    return safe_get_json(f"{settings.hh_base_url}/vacancies/{vacancy_id}", settings, headers=build_hh_headers(settings))


def parse_fl_budget(text: str | None) -> int | None:
    if not text:
        return None
    value = html.unescape(str(text))
    match = re.search(r"бюджет\s*:\s*([\d\s\u00a0]+)", value, flags=re.IGNORECASE)
    if not match:
        return None
    digits = re.sub(r"\D+", "", match.group(1))
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def extract_fl_project_id(url: str | None) -> str | None:
    if not url:
        return None
    match = re.search(r"/projects/(\d+)/", str(url))
    if match:
        return match.group(1)
    return None


def normalize_fl_rss_item(item) -> dict:
    title = html.unescape(item.findtext("title") or "").strip()
    description = html.unescape(item.findtext("description") or "").strip()
    category = html.unescape(item.findtext("category") or "").strip()
    link = (item.findtext("link") or item.findtext("guid") or "").strip()
    published_at = (item.findtext("pubDate") or "").strip()
    budget = parse_fl_budget(title) or parse_fl_budget(description)
    return {
        "source": "fl",
        "source_name": "FL.ru",
        "source_vacancy_id": extract_fl_project_id(link),
        "title": title,
        "company_name": None,
        "location": None,
        "work_format": "Удалёнка",
        "experience": None,
        "salary_from": budget,
        "salary_to": budget,
        "currency": "RUB" if budget is not None else None,
        "published_at": published_at,
        "url": link,
        "description": clean_html(description),
        "category": category,
    }


def fetch_fl_with_info(profile: dict, settings: Settings, limit: int | None = None) -> tuple[list[dict], dict]:
    del profile
    effective_limit = limit or settings.per_source_cache
    xml_text = safe_get_text(settings.fl_rss_url, settings, headers={"User-Agent": settings.fl_user_agent})
    if xml_text is None:
        return [], {"source": "fl", "source_name": "FL.ru", "error": "request_failed", "url": settings.fl_rss_url, "items": 0}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.warning("FL RSS parse failed: %s", exc)
        return [], {"source": "fl", "source_name": "FL.ru", "error": "parse_failed", "url": settings.fl_rss_url, "items": 0}
    items = root.findall("./channel/item")
    normalized = [normalize_fl_rss_item(item) for item in items[:effective_limit]]
    return normalized, {
        "source": "fl",
        "source_name": "FL.ru",
        "items": len(normalized),
        "limit": effective_limit,
        "url": settings.fl_rss_url,
    }


def parse_freelance_ru_budget(cost_text: str | None) -> tuple[int | None, int | None, str | None]:
    value = clean_html(cost_text or "")
    if not value:
        return None, None, None
    if "договор" in value.lower():
        return None, None, None
    numbers = []
    for raw in re.findall(r"\d[\d\s\u00a0]*", value):
        digits = re.sub(r"\D+", "", raw)
        if digits:
            try:
                numbers.append(int(digits))
            except ValueError:
                continue
    if not numbers:
        return None, None, None
    if len(numbers) == 1:
        return numbers[0], numbers[0], "RUB"
    return min(numbers), max(numbers), "RUB"


def extract_freelance_ru_project_id(url: str | None) -> str | None:
    if not url:
        return None
    match = re.search(r"-(\d+)\.html(?:\?.*)?$", str(url))
    if match:
        return match.group(1)
    return None


def normalize_freelance_ru_url(url: str | None) -> str | None:
    if not url:
        return None
    value = str(url).strip()
    if value.startswith("//"):
        return "https:" + value
    if value.startswith(("http://", "https://")):
        return value
    if value.startswith("/"):
        return "https://www.freelance.ru" + value
    return "https://www.freelance.ru/" + value.lstrip("/")


def parse_freelance_ru_card(chunk: str) -> dict | None:
    title_match = re.search(
        r'<h2 class="title[^"]*"[^>]*>.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        chunk,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not title_match:
        return None
    url = normalize_freelance_ru_url(title_match.group(1))
    title = clean_html(title_match.group(2))
    desc_match = re.search(r'<a class="description"[^>]*>(.*?)</a>', chunk, flags=re.IGNORECASE | re.DOTALL)
    category_match = re.search(r'<div class="specs-list">.*?<b[^>]*>(.*?)</b>', chunk, flags=re.IGNORECASE | re.DOTALL)
    cost_match = re.search(r'<div class="cost">\s*(.*?)\s*</div>', chunk, flags=re.IGNORECASE | re.DOTALL)
    owner_match = re.search(r'<span class="user-name">\s*(.*?)\s*</span>', chunk, flags=re.IGNORECASE | re.DOTALL)
    time_match = re.search(r'<time[^>]*class="timeago"[^>]*datetime="([^"]+)"', chunk, flags=re.IGNORECASE | re.DOTALL)
    publish_fallback_match = re.search(r'<div[^>]*class="publish-time"[^>]*title="([^"]+)"', chunk, flags=re.IGNORECASE | re.DOTALL)

    cost_text = clean_html(cost_match.group(1)) if cost_match else ""
    salary_from, salary_to, currency = parse_freelance_ru_budget(cost_text)
    published_at = time_match.group(1).strip() if time_match else None
    if not published_at and publish_fallback_match:
        published_at = clean_html(publish_fallback_match.group(1))

    return {
        "source": "freelance_ru",
        "source_name": "Freelance.ru",
        "source_vacancy_id": extract_freelance_ru_project_id(url),
        "title": title,
        "company_name": clean_html(owner_match.group(1)) if owner_match else None,
        "location": None,
        "work_format": "Удалёнка",
        "experience": None,
        "salary_from": salary_from,
        "salary_to": salary_to,
        "currency": currency,
        "published_at": published_at,
        "url": url,
        "description": clean_html(desc_match.group(1)) if desc_match else "",
        "category": clean_html(category_match.group(1)) if category_match else "",
        "price_text": cost_text or None,
    }


def parse_freelance_ru_search(html_text: str, limit: int) -> list[dict]:
    if not html_text:
        return []
    marker = '<div class="project-item-default-card project '
    results = []
    for part in html_text.split(marker)[1:]:
        card = parse_freelance_ru_card(marker + part)
        if not card:
            continue
        results.append(card)
        if len(results) >= limit:
            break
    return results


def fetch_freelance_ru_with_info(profile: dict, settings: Settings, limit: int | None = None) -> tuple[list[dict], dict]:
    effective_limit = limit or settings.per_source_cache
    query = build_query(profile)
    params = {}
    if settings.freelance_ru_open_for_all_only:
        params["a"] = 1
    if query:
        params["q"] = query
    html_text = safe_get_text(
        settings.freelance_ru_search_url,
        settings,
        params=params or None,
        headers={"User-Agent": settings.freelance_ru_user_agent},
    )
    if html_text is None:
        return [], {
            "source": "freelance_ru",
            "source_name": "Freelance.ru",
            "error": "request_failed",
            "url": settings.freelance_ru_search_url,
            "query": query,
            "open_for_all_only": settings.freelance_ru_open_for_all_only,
            "items": 0,
        }
    items = parse_freelance_ru_search(html_text, limit=effective_limit)
    return items, {
        "source": "freelance_ru",
        "source_name": "Freelance.ru",
        "url": settings.freelance_ru_search_url,
        "query": query,
        "open_for_all_only": settings.freelance_ru_open_for_all_only,
        "items": len(items),
        "limit": effective_limit,
    }
