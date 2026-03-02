import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    return int(value)


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    return float(value)


@dataclass(frozen=True)
class Settings:
    bot_token: str | None
    pg_dsn: str | None
    hh_base_url: str
    hh_token: str | None
    hh_user_agent: str
    fl_rss_url: str
    fl_user_agent: str
    freelance_ru_search_url: str
    freelance_ru_user_agent: str
    freelance_ru_open_for_all_only: bool
    enable_fl_source: bool
    enable_freelance_ru_source: bool
    request_timeout: int
    max_query_skills: int
    vacancy_cache_size: int
    per_source_cache: int
    fetch_attempts: int
    max_seen_per_user: int
    match_threshold: float
    skills_sample_ratio: float
    vacancy_cache_ttl: int
    hh_page_range: int
    auto_push_enabled: bool
    auto_push_interval_seconds: int
    auto_push_max_per_cycle: int

    def validate(self) -> None:
        if not self.bot_token:
            raise RuntimeError("BOT_TOKEN is missing in .env")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv()
    vacancy_cache_size = _env_int("VACANCY_CACHE_SIZE", 15)
    return Settings(
        bot_token=os.getenv("BOT_TOKEN"),
        pg_dsn=os.getenv("PG_DSN"),
        hh_base_url=os.getenv("HH_BASE_URL", "https://api.hh.ru").rstrip("/"),
        hh_token=os.getenv("HH_TOKEN"),
        hh_user_agent=os.getenv("HH_USER_AGENT", "VacancyBot/0.1"),
        fl_rss_url=os.getenv("FL_RSS_URL", "https://www.fl.ru/rss/all.xml?category=5"),
        fl_user_agent=os.getenv("FL_USER_AGENT", os.getenv("HH_USER_AGENT", "VacancyBot/0.1")),
        freelance_ru_search_url=os.getenv("FREELANCE_RU_SEARCH_URL", "https://www.freelance.ru/project/search"),
        freelance_ru_user_agent=os.getenv("FREELANCE_RU_USER_AGENT", os.getenv("HH_USER_AGENT", "VacancyBot/0.1")),
        freelance_ru_open_for_all_only=_env_bool("FREELANCE_RU_OPEN_FOR_ALL_ONLY", True),
        enable_fl_source=_env_bool("ENABLE_FL_SOURCE", True),
        enable_freelance_ru_source=_env_bool("ENABLE_FREELANCE_RU_SOURCE", True),
        request_timeout=_env_int("REQUEST_TIMEOUT", 15),
        max_query_skills=5,
        vacancy_cache_size=vacancy_cache_size,
        per_source_cache=_env_int("PER_SOURCE_CACHE", vacancy_cache_size),
        fetch_attempts=_env_int("FETCH_ATTEMPTS", 3),
        max_seen_per_user=_env_int("MAX_SEEN_PER_USER", 500),
        match_threshold=_env_float("MATCH_THRESHOLD", 0.5),
        skills_sample_ratio=_env_float("SKILLS_SAMPLE_RATIO", 0.5),
        vacancy_cache_ttl=_env_int("VACANCY_CACHE_TTL", 600),
        hh_page_range=max(_env_int("HH_PAGE_RANGE", 4), 0),
        auto_push_enabled=_env_bool("AUTO_PUSH_ENABLED", True),
        auto_push_interval_seconds=max(_env_int("AUTO_PUSH_INTERVAL_SECONDS", 300), 30),
        auto_push_max_per_cycle=max(_env_int("AUTO_PUSH_MAX_PER_CYCLE", 3), 1),
    )
