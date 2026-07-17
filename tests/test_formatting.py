"""Тесты форматтеров канала: стиль, экранирование, усечение."""

from datetime import UTC, datetime

from app.db.models import AlertLevel, CorridorLeg, NewsItem, Port
from app.integrations.weather.base import WindObservation
from app.services.formatting import (
    format_manual_report,
    format_news_item,
    format_weather_alert,
)

TS = datetime(2026, 7, 17, 9, 40, tzinfo=UTC)


def _port(leg: CorridorLeg = CorridorLeg.caspian) -> Port:
    return Port(code="AKTAU", name="Актау", country="Казахстан", leg=leg, lat=43.63, lon=51.25)


def test_weather_alert_format() -> None:
    obs = WindObservation(wind_speed=15.0, wind_gust=19.0, wind_dir=210.0, ts=TS)
    text = format_weather_alert(_port(), AlertLevel.warning, obs)
    assert text.startswith("⚠️ <b>Актау — риск остановки операций</b>")
    assert "Ветер 15 м/с, порывы до 19 м/с" in text
    assert "паромов" in text  # каспийское плечо — про паромы
    assert "17.07 09:40 UTC" in text


def test_weather_alert_black_sea_phrase() -> None:
    obs = WindObservation(wind_speed=18.0, wind_gust=22.0, wind_dir=210.0, ts=TS)
    text = format_weather_alert(_port(CorridorLeg.black_sea), AlertLevel.critical, obs)
    assert text.startswith("🔴")
    assert "судозаходов" in text


def test_news_item_escapes_html() -> None:
    item = NewsItem(
        source="middlecorridor.com",
        url="https://example.com/a?b=1&c=2",
        title="TITR <объёмы> выросли & растут",
        summary="Подробности <тут>",
    )
    text = format_news_item(item)
    assert "&lt;объёмы&gt;" in text
    assert "&amp; растут" in text
    assert "<объёмы>" not in text
    assert 'href="https://example.com/a?b=1&amp;c=2"' in text


def test_news_item_without_summary() -> None:
    item = NewsItem(source="timesca.com", url="https://example.com/x", title="Заголовок")
    assert format_news_item(item).count("\n") == 1  # заголовок + ссылка


def test_manual_report_queue_payload() -> None:
    text = format_manual_report(
        "queue",
        {"vessels_waiting": 4, "ferry_expected": "2026-07-18"},
        note=None,
        ts=TS,
        port_name="Актау",
    )
    assert text.startswith("<b>⚓️ Очередь — Актау</b>")
    assert "Судов в ожидании: 4" in text
    assert "Паром ожидается: 2026-07-18" in text
    assert "доверенного источника" in text


def test_manual_report_escapes_note_and_unknown_keys() -> None:
    text = format_manual_report(
        "note",
        {"custom<key>": "<b>значение</b>"},
        note="Комментарий с <html> & символами",
        ts=TS,
    )
    assert "custom&lt;key&gt;" in text
    assert "&lt;b&gt;значение&lt;/b&gt;" in text
    assert "&lt;html&gt; &amp; символами" in text


def test_long_summary_truncated() -> None:
    item = NewsItem(source="s", url="https://example.com/y", title="t", summary="ы" * 1000)
    text = format_news_item(item)
    assert "…" in text
    assert len(text) < 600
