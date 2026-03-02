from app.config import Settings
from app.services.matching import filter_vacancies_by_profile, normalize_skills_list


def build_settings(**overrides) -> Settings:
    data = {
        "bot_token": "token",
        "pg_dsn": None,
        "hh_base_url": "https://api.hh.ru",
        "hh_token": None,
        "hh_user_agent": "VacancyBot/0.1",
        "fl_rss_url": "https://www.fl.ru/rss/all.xml?category=5",
        "fl_user_agent": "VacancyBot/0.1",
        "freelance_ru_search_url": "https://www.freelance.ru/project/search",
        "freelance_ru_user_agent": "VacancyBot/0.1",
        "freelance_ru_open_for_all_only": True,
        "enable_fl_source": True,
        "enable_freelance_ru_source": True,
        "request_timeout": 15,
        "max_query_skills": 5,
        "vacancy_cache_size": 15,
        "per_source_cache": 15,
        "fetch_attempts": 3,
        "max_seen_per_user": 500,
        "match_threshold": 0.5,
        "skills_sample_ratio": 1.0,
        "vacancy_cache_ttl": 600,
        "hh_page_range": 4,
        "auto_push_enabled": True,
        "auto_push_interval_seconds": 300,
        "auto_push_max_per_cycle": 3,
    }
    data.update(overrides)
    return Settings(**data)


def test_normalize_skills_list_removes_case_duplicates():
    assert normalize_skills_list(["Python", "python", " FastAPI ", "", "FASTAPI"]) == ["Python", "FastAPI"]


def test_filter_vacancies_by_profile_keeps_only_matching_items():
    settings = build_settings(match_threshold=0.6)
    profile = {
        "desired_role": "Python backend developer",
        "skills": ["Python", "FastAPI", "PostgreSQL"],
        "stop_words": ["php"],
        "blacklisted_companies": ["BadCorp"],
        "min_salary": 120000,
    }
    vacancies = [
        {
            "title": "Python FastAPI Developer",
            "description": "Backend service with Python, FastAPI and PostgreSQL",
            "company_name": "GoodCorp",
            "salary_from": 150000,
            "salary_to": 180000,
        },
        {
            "title": "PHP Developer",
            "description": "Legacy backend",
            "company_name": "GoodCorp",
            "salary_from": 200000,
            "salary_to": 220000,
        },
        {
            "title": "Python Developer",
            "description": "FastAPI and PostgreSQL stack",
            "company_name": "BadCorp LLC",
            "salary_from": 200000,
            "salary_to": 220000,
        },
    ]

    filtered = filter_vacancies_by_profile(profile, vacancies, settings)

    assert len(filtered) == 1
    assert filtered[0]["company_name"] == "GoodCorp"
    assert filtered[0]["match_ratio"] == 1.0
