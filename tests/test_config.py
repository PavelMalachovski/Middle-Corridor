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


def test_cors_origins_parsed_from_csv() -> None:
    settings = _settings(cors_origins="https://a.vercel.app, https://b.example")
    assert settings.cors_origins == ["https://a.vercel.app", "https://b.example"]
    assert _settings().cors_origins == []


def test_requirements_mirror_pyproject() -> None:
    """requirements.txt нужен Vercel; источник истины — pyproject.toml."""
    import tomllib
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    declared = pyproject["project"]["dependencies"]
    listed = [
        line.strip()
        for line in (root / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert listed == declared
