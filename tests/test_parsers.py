from app.clients.vacancy_sources import parse_freelance_ru_search


def test_parse_freelance_ru_search_extracts_project_card():
    html = """
    <div class="project-item-default-card project ">
      <h2 class="title">
        <a href="/projects/backend-bot-1234567.html">Python Backend Bot</a>
      </h2>
      <div class="specs-list"><b>Telegram bots</b></div>
      <div class="cost">120 000 руб.</div>
      <span class="user-name">Acme Studio</span>
      <time class="timeago" datetime="2026-03-01T10:00:00+03:00"></time>
      <a class="description">Need Python, FastAPI and PostgreSQL skills</a>
    </div>
    """

    items = parse_freelance_ru_search(html, limit=5)

    assert len(items) == 1
    assert items[0]["source"] == "freelance_ru"
    assert items[0]["title"] == "Python Backend Bot"
    assert items[0]["company_name"] == "Acme Studio"
    assert items[0]["salary_from"] == 120000
    assert items[0]["currency"] == "RUB"
