"""Мок-точность прогноза: синтетические шторма → тот же score_events, что в бою."""

import statistics
from datetime import UTC, datetime, timedelta

import httpx

from app.api.main import create_app
from app.config import Settings
from app.integrations.mock.accuracy import MockAccuracySource
from app.main import build_map_service

NOW = datetime(2026, 11, 1, 15, 0, tzinfo=UTC)


async def _ports(clock_now: datetime = NOW):
    return await MockAccuracySource(lambda: clock_now).accuracy(90)


async def test_mock_accuracy_deterministic() -> None:
    a = await _ports()
    b = await _ports()
    assert [(p.code, p.score) for p in a] == [(p.code, p.score) for p in b]


async def test_mock_accuracy_stable_within_day() -> None:
    a = await _ports(NOW.replace(hour=1))
    b = await _ports(NOW.replace(hour=23))
    assert [p.score for p in a] == [p.score for p in b]


async def test_mock_accuracy_plausible() -> None:
    ports = await _ports()
    closures = sum(p.score.closures for p in ports)
    hits = sum(p.score.hits for p in ports)
    episodes = sum(p.score.episodes for p in ports)
    false_alarms = sum(p.score.false_alarms for p in ports)
    leads = [lead for p in ports for lead in p.score.lead_hours]
    assert closures >= 20  # на 90 днях по коридору — десятки остановок
    assert 0.7 <= hits / closures <= 0.9
    assert 0.15 <= false_alarms / episodes <= 0.4
    assert 6 <= statistics.median(leads) <= 24
    assert {p.code for p in ports} >= {"AKTAU", "KURYK", "BAKU_ALAT", "POTI", "CONSTANTA"}


async def test_port_without_storms_none() -> None:
    source = MockAccuracySource(lambda: NOW, storms_per_week={"AKTAU": 0})
    aktau = next(p for p in await source.accuracy(90) if p.code == "AKTAU")
    assert aktau.score.closures == 0
    assert aktau.score.pod is None


async def test_accuracy_endpoint_mock_demo() -> None:
    settings = Settings(_env_file=None, mock_data=True, web_dist_dir="")
    app = create_app(
        settings=settings,
        map_service=build_map_service(settings, None),
        accuracy_service=MockAccuracySource(),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as client:
        res = await client.get("/api/v1/accuracy")
    assert res.status_code == 200
    body = res.json()
    assert body["demo"] is True
    assert any(p["code"] == "AKTAU" for p in body["ports"])


async def test_mock_accuracy_plausible_every_day_for_a_year() -> None:
    """Правдоподобно в любой день показа, а не только в день написания теста."""
    bad: list[str] = []
    for day in range(365):
        when = NOW - timedelta(days=day)
        ports = await MockAccuracySource(lambda when=when: when).accuracy(90)
        closures = sum(p.score.closures for p in ports)
        hits = sum(p.score.hits for p in ports)
        episodes = sum(p.score.episodes for p in ports)
        false_alarms = sum(p.score.false_alarms for p in ports)
        pod, far = hits / closures, false_alarms / episodes
        if not (0.7 <= pod <= 0.9 and 0.15 <= far <= 0.4):
            bad.append(f"{when:%Y-%m-%d} pod={pod:.2f} far={far:.2f}")
        for p in ports:  # «POD 100 %, ноль ложных тревог» у порта с заметной историей — анти-цель
            if p.score.closures >= 3 and p.score.pod == 1.0 and p.score.false_alarms == 0:
                bad.append(f"{when:%Y-%m-%d} {p.code} идеален")
    assert not bad, bad[:5]
