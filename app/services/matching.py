import hashlib
import math

from app.config import Settings
from app.utils.text import clean_html, extract_tokens


def build_query(profile: dict) -> str:
    role = (profile.get("desired_role") or "").strip()
    if role:
        return role
    skills = profile.get("skills") or []
    if not isinstance(skills, list):
        skills = [skills]
    for skill in skills:
        value = str(skill).strip()
        if value:
            return value
    return ""


def normalize_match_text(vacancy: dict) -> str:
    title = vacancy.get("title") or ""
    description = vacancy.get("description") or vacancy.get("description_snippet") or ""
    return clean_html(f"{title}\n{description}").lower()


def normalize_skills_list(skills) -> list[str]:
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


def sample_skills(skills, ratio: float, seed) -> list[str]:
    if not skills:
        return []
    ratio = max(0.0, min(1.0, ratio))
    normalized = normalize_skills_list(skills)
    if not normalized:
        return []
    limit = int(math.ceil(len(normalized) * ratio))
    limit = max(1, min(len(normalized), limit))
    if limit >= len(normalized):
        return normalized

    def sort_key(skill: str) -> str:
        payload = f"{seed}|{skill.lower()}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    return sorted(normalized, key=sort_key)[:limit]


def skill_in_text(skill: str, text: str, tokens: set[str]) -> bool:
    value = str(skill).strip().lower()
    if not value:
        return False
    if " " in value:
        return value in text
    if any(char in value for char in ".-/:"):
        if value in text:
            return True
        parts = extract_tokens(value)
        return bool(parts) and all(part in tokens for part in parts)
    return value in tokens


def skill_match_ratio(skills, text: str, tokens: set[str]) -> float:
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


def role_match(text: str, tokens: set[str], role: str) -> bool:
    role_value = (role or "").strip().lower()
    if not role_value:
        return True
    if role_value in text:
        return True
    words = [word for word in extract_tokens(role_value) if len(word) >= 2]
    if not words:
        return False
    return any(word in tokens for word in words)


def compute_match_stats(profile: dict, vacancy: dict) -> tuple[int, int, int, float]:
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
    matched = sum(1 for skill in unique_skills if skill_in_text(skill, text, tokens))
    return matched, raw_total, unique_total, matched / unique_total


def compute_match_ratio(profile: dict, vacancy: dict, settings: Settings) -> float:
    skills = profile.get("skills") or []
    if not isinstance(skills, list):
        skills = [skills]
    role = profile.get("desired_role") or ""
    text = normalize_match_text(vacancy)
    tokens = extract_tokens(text)
    if skills:
        seed = vacancy.get("source_vacancy_id") or vacancy.get("url") or vacancy.get("title") or ""
        sampled = sample_skills(skills, settings.skills_sample_ratio, seed)
        return skill_match_ratio(sampled, text, tokens)
    return 1.0 if role_match(text, tokens, role) else 0.0


def vacancy_text_blob(vacancy: dict) -> str:
    parts = [
        vacancy.get("title") or "",
        vacancy.get("description") or vacancy.get("description_snippet") or "",
        vacancy.get("company_name") or "",
        vacancy.get("category") or "",
    ]
    return clean_html("\n".join(str(part) for part in parts if part)).lower()


def contains_stop_word(profile: dict, vacancy: dict) -> bool:
    stop_words = profile.get("stop_words") or []
    if not isinstance(stop_words, list):
        stop_words = [stop_words]
    terms = [str(word).strip().lower() for word in stop_words if str(word).strip()]
    if not terms:
        return False
    text = vacancy_text_blob(vacancy)
    return any(term in text for term in terms)


def is_blacklisted_company(profile: dict, vacancy: dict) -> bool:
    blacklist = profile.get("blacklisted_companies") or []
    if not isinstance(blacklist, list):
        blacklist = [blacklist]
    company = (vacancy.get("company_name") or "").strip().lower()
    if not company:
        return False
    terms = [str(word).strip().lower() for word in blacklist if str(word).strip()]
    return any(term and term in company for term in terms)


def meets_min_budget(profile: dict, vacancy: dict) -> bool:
    min_salary = profile.get("min_salary")
    if min_salary in (None, "", 0):
        return True
    try:
        min_value = int(min_salary)
    except (TypeError, ValueError):
        return True
    values = [value for value in [vacancy.get("salary_from"), vacancy.get("salary_to")] if isinstance(value, (int, float))]
    if not values:
        return False
    return max(values) >= min_value


def filter_vacancies_by_profile(profile: dict, vacancies: list[dict], settings: Settings) -> list[dict]:
    skills = profile.get("skills") or []
    if not isinstance(skills, list):
        skills = [skills]
    filtered = []
    for vacancy in vacancies:
        if contains_stop_word(profile, vacancy):
            continue
        if is_blacklisted_company(profile, vacancy):
            continue
        if not meets_min_budget(profile, vacancy):
            continue
        if skills:
            ratio = compute_match_ratio(profile, vacancy, settings)
            if ratio < settings.match_threshold:
                continue
            vacancy["match_ratio"] = ratio
        else:
            ratio = compute_match_ratio(profile, vacancy, settings)
            if ratio <= 0.0:
                continue
            vacancy["match_ratio"] = 1.0
        filtered.append(vacancy)
    return filtered
