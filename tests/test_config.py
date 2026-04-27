from app.config import get_settings


def test_get_settings_reads_env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_PROXY_URL", "socks5h://127.0.0.1:1080")
    monkeypatch.setenv("HH_USER_AGENT", "VacancyBot/test")
    monkeypatch.setenv("MATCH_THRESHOLD", "0.75")
    monkeypatch.setenv("AUTO_PUSH_MAX_PER_CYCLE", "7")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.bot_token == "test-token"
    assert settings.telegram_proxy_url == "socks5h://127.0.0.1:1080"
    assert settings.hh_user_agent == "VacancyBot/test"
    assert settings.match_threshold == 0.75
    assert settings.auto_push_max_per_cycle == 7

    get_settings.cache_clear()
