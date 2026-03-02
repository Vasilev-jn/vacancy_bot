import html
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


def parse_list(text: str) -> list[str]:
    return [item.strip() for item in text.split(",") if item.strip()]


def parse_salary(text: str) -> int | None:
    cleaned = text.replace(" ", "").replace("_", "")
    try:
        return int(cleaned)
    except ValueError:
        return None


def format_value(value) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "не указано"
    if value is None or value == "":
        return "не указано"
    return str(value)


def escape_text(value) -> str:
    if value is None:
        return ""
    return html.escape(str(value))


def clean_html(text: str | None) -> str:
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


def limit_text(text: str | None, limit: int = 3800) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def extract_tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9+#]+", text.lower()))


def format_salary(salary_from=None, salary_to=None, currency=None) -> str:
    currency_label = "₽" if str(currency or "").upper() == "RUB" else (currency or "")
    if salary_from is None and salary_to is None:
        return "не указана"
    if salary_from is not None and salary_to is not None and salary_from == salary_to:
        return f"{salary_from} {currency_label}".strip()
    if salary_from and salary_to:
        return f"{salary_from}–{salary_to} {currency_label}".strip()
    if salary_from:
        return f"от {salary_from} {currency_label}".strip()
    return f"до {salary_to} {currency_label}".strip()


def parse_datetime_value(value):
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(text)
        if dt and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        return None


def format_age_short(dt) -> str | None:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    delta_seconds = int((now - dt.astimezone(timezone.utc)).total_seconds())
    if delta_seconds < 60:
        return "только что"
    minutes = delta_seconds // 60
    if minutes < 60:
        return f"{minutes}м назад"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}ч назад"
    days = hours // 24
    if days < 7:
        return f"{days}д назад"
    weeks = days // 7
    if weeks < 5:
        return f"{weeks}н назад"
    months = days // 30
    if months < 12:
        return f"{months}мес назад"
    years = days // 365
    return f"{years}г назад"


def format_published_at_display(value) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "не указано"
    dt = parse_datetime_value(raw)
    if not dt:
        return raw
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    exact = dt.strftime("%Y-%m-%d %H:%M")
    offset = dt.strftime("%z")
    if offset and len(offset) == 5:
        offset = offset[:3] + ":" + offset[3:]
        exact = f"{exact} {offset}"
    age = format_age_short(dt)
    if age:
        return f"{exact} ({age})"
    return exact
