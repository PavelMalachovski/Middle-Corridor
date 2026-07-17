"""Тесты конфигурации: разбор списков из ENV-строк."""

from app.config import Settings


def _settings(**kwargs: object) -> Settings:
    # _env_file=None — не подхватывать локальный .env в тестах
    return Settings(_env_file=None, **kwargs)  # type: ignore[call-arg]


def test_admin_ids_parsed_from_comma_separated() -> None:
    settings = _settings(admin_user_ids="123, 456,789")
    assert settings.admin_user_ids == [123, 456, 789]


def test_admin_ids_empty_string() -> None:
    settings = _settings(admin_user_ids="")
    assert settings.admin_user_ids == []


def test_news_sources_parsed_and_stripped() -> None:
    settings = _settings(news_sources=" https://a.example/rss , https://b.example/feed ")
    assert settings.news_sources == ["https://a.example/rss", "https://b.example/feed"]


def test_weather_thresholds_defaults() -> None:
    settings = _settings()
    assert settings.weather_watch_wind == 10.0
    assert settings.weather_warning_wind == 13.8
    assert settings.weather_critical_gust == 21.0
