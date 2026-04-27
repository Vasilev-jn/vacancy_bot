from app.clients.vacancy_sources import fetch_hh_with_info
from app.services.vacancies import build_vacancy_text
from tests.test_matching import build_settings


def test_fetch_hh_with_info_normalizes_vacancy(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "pages": 1,
                "items": [
                    {
                        "id": "123",
                        "name": "Python Backend Developer",
                        "employer": {"name": "Acme"},
                        "area": {"name": "Москва"},
                        "schedule": {"name": "Удаленная работа"},
                        "experience": {"name": "1-3 года"},
                        "salary": {"from": 150000, "to": 180000, "currency": "RUR"},
                        "alternate_url": "https://hh.ru/vacancy/123",
                        "snippet": {"requirement": "Python, FastAPI"},
                    }
                ],
            }

    def fake_get(url, params=None, headers=None, timeout=None):
        assert url == "https://api.hh.ru/vacancies"
        assert params["text"] == "Python"
        assert headers == {"User-Agent": "VacancyBot/0.1"}
        return Response()

    monkeypatch.setattr("app.clients.vacancy_sources._direct_session.get", fake_get)
    settings = build_settings(hh_page_range=1)
    profile = {"desired_role": "Python", "min_salary": None}

    items, info = fetch_hh_with_info(profile, settings, limit=5)

    assert len(items) == 1
    assert info["source"] == "hh"
    assert items[0]["source"] == "hh"
    assert items[0]["source_vacancy_id"] == "123"
    assert items[0]["title"] == "Python Backend Developer"
    assert items[0]["company_name"] == "Acme"
    assert items[0]["salary_from"] == 150000


def test_build_vacancy_text_formats_hh_card():
    text = build_vacancy_text(
        {
            "source_name": "HH.ru",
            "title": "Python Backend Developer",
            "company_name": "Acme",
            "location": "Москва",
            "work_format": "Удалёнка",
            "experience": "1-3 года",
            "salary_from": 150000,
            "salary_to": 180000,
            "currency": "RUR",
            "match_count": 2,
            "match_total": 3,
        }
    )

    assert "Формат: Удалёнка" in text
    assert "Источник: HH.ru" in text
    assert "Совпадения навыков: 2 из 3" in text
    assert "???" not in text
