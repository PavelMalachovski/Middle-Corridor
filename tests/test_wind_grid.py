"""Поле ветра над морями: маска, клиент Open-Meteo по сетке, снимки в БД, replay."""

import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integrations.weather.base import GridPointForecast, WindObservation
from app.integrations.weather.open_meteo import GRID_BATCH, OpenMeteoProvider
from app.services.corridor import COAST_TOLERANCE_DEG, sea_at, sea_grid
from app.services.wind_grid import WindGridService

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
H = timedelta(hours=1)


class FakeGridProvider:
    """Детерминированный прогноз: скорость = час + широта/10, направление = долгота."""

    def __init__(self, start: datetime = NOW, hours: int = 6) -> None:
        self.start = start
        self.hours = hours
        self.calls = 0

    async def get_wind_grid(
        self, points: list[tuple[float, float]], forecast_hours: int
    ) -> list[GridPointForecast]:
        self.calls += 1
        n = min(self.hours, forecast_hours)
        return [
            GridPointForecast(
                lat=lat,
                lon=lon,
                hours=[
                    WindObservation(
                        wind_speed=i + lat / 10,
                        wind_gust=i + lat / 10 + 3,
                        wind_dir=lon % 360,
                        ts=self.start + i * H,
                    )
                    for i in range(n)
                ],
            )
            for lat, lon in points
        ]


def _service(
    session_factory: async_sessionmaker[AsyncSession],
    provider: FakeGridProvider | None,
    clock: datetime = NOW,
    **kwargs: object,
) -> WindGridService:
    return WindGridService(session_factory, provider, step_deg=1.0, clock=lambda: clock, **kwargs)


async def test_open_meteo_grid_batches_points_and_keeps_order() -> None:
    requests: list[dict[str, list[str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = parse_qs(request.url.query.decode())
        requests.append(params)
        lats = params["latitude"][0].split(",")
        lons = params["longitude"][0].split(",")
        assert len(lats) == len(lons) <= GRID_BATCH
        body = [
            {
                "latitude": float(lat),
                "longitude": float(lon),
                "hourly": {
                    "time": ["2026-09-05T12:00", "2026-09-05T13:00", "2026-09-05T14:00"],
                    "wind_speed_10m": [5.0, 6.0, None],  # null-хвост
                    "wind_gusts_10m": [8.0, 9.0, None],
                    "wind_direction_10m": [270, 280, None],
                },
            }
            for lat, lon in zip(lats, lons, strict=True)
        ]
        return httpx.Response(200, content=json.dumps(body))

    provider = OpenMeteoProvider(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    points = [(40.0 + i * 0.01, 50.0) for i in range(GRID_BATCH + 5)]
    out = await provider.get_wind_grid(points, forecast_hours=3)
    assert len(requests) == 2  # 105 точек → батчи 100 + 5
    assert [(p.lat, p.lon) for p in out] == points
    assert [h.wind_speed for h in out[0].hours] == [5.0, 6.0]
    assert out[0].hours[1].ts == datetime(2026, 9, 5, 13, tzinfo=UTC)
    assert requests[0]["wind_speed_unit"] == ["ms"] and requests[0]["hourly"]


async def test_refresh_stores_snapshot_and_field_follows_at(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    provider = FakeGridProvider()
    service = _service(session_factory, provider)
    stored = await service.refresh_once()
    assert stored == len(sea_grid(1.0)) and provider.calls == 1

    field = await service.get_field()
    assert field is not None and field.ts == NOW and field.step_deg == 1.0
    assert len(field.points) == stored
    assert all(sea_at(p.lat, p.lon, COAST_TOLERANCE_DEG) for p in field.points)
    aktau = next(p for p in field.points if (p.lat, p.lon) == (44.0, 50.0))
    assert aktau.speed == round(0 + 4.4, 1) and aktau.dir == 50

    # будущее в пределах прогноза — тот час из снимка
    later = await service.get_field(at=NOW + 2 * H + timedelta(minutes=20))
    assert later is not None and later.ts == NOW + 2 * H
    assert next(p for p in later.points if (p.lat, p.lon) == (44.0, 50.0)).speed == 6.4
    # за горизонтом прогноза — нет данных
    assert await service.get_field(at=NOW + 12 * H) is None
    # грубее шаг — прореживание по кратным
    coarse = await service.get_field(step_deg=2.0)
    assert coarse is not None and coarse.step_deg == 2.0
    assert 0 < len(coarse.points) < len(field.points)
    assert all(p.lat % 2 == 0 and p.lon % 2 == 0 for p in coarse.points)
    # мельче шага снимка не станет
    fine = await service.get_field(step_deg=0.25)
    assert fine is not None and fine.step_deg == 1.0


async def test_history_serves_replay_and_expires(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    first = FakeGridProvider(start=NOW)
    await _service(session_factory, first).refresh_once()
    service = _service(session_factory, FakeGridProvider(start=NOW + 3 * H), clock=NOW + 3 * H)
    await service.refresh_once()

    # момент между снимками — из первого снимка (прогноз, каким он был тогда)
    between = await service.get_field(at=NOW + 1 * H)
    assert between is not None and between.ts == NOW + 1 * H
    assert next(p for p in between.points if (p.lat, p.lon) == (44.0, 50.0)).speed == 5.4
    # «сейчас» — из свежего
    now_field = await service.get_field()
    assert now_field is not None and now_field.ts == NOW + 3 * H
    # раньше всех снимков и их часов — нет данных
    assert await service.get_field(at=NOW - 10 * H) is None

    # снимки старше history_hours удаляются при следующем обновлении
    third = _service(
        session_factory, FakeGridProvider(start=NOW + 6 * H), clock=NOW + 6 * H, history_hours=2
    )
    await third.refresh_once()
    assert await third.get_field(at=NOW + 1 * H) is None  # первые два снимка ушли
    fresh = await third.get_field()
    assert fresh is not None and fresh.ts == NOW + 6 * H


async def test_lazy_refresh_fetches_once_when_empty(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    provider = FakeGridProvider()
    service = _service(session_factory, provider)
    assert (await service.get_field()) is not None
    assert provider.calls == 1
    assert (await service.get_field()) is not None
    assert provider.calls == 1  # свежий снимок есть — повторно не ходим
    # без ленивого режима и без снимков — «нет данных», провайдер не тронут
    quiet = _service(session_factory, FakeGridProvider(), lazy_refresh=False)
    assert await quiet.get_field(at=NOW - 200 * H) is None


async def test_without_provider_field_is_none(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = _service(session_factory, None)
    assert await service.refresh_once() == 0
    assert await service.get_field() is None
