from app.config import get_settings


def test_get_settings_reads_env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "test-token")
    monkeypatch.setenv("MATCH_THRESHOLD", "0.75")
    monkeypatch.setenv("ENABLE_FL_SOURCE", "0")
    monkeypatch.setenv("AUTO_PUSH_MAX_PER_CYCLE", "7")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.bot_token == "test-token"
    assert settings.match_threshold == 0.75
    assert settings.enable_fl_source is False
    assert settings.auto_push_max_per_cycle == 7

    get_settings.cache_clear()
