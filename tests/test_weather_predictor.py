"""Тесты ядра: пороги, переходы уровней, антиспам, отбой (§7.1)."""

from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import AlertLevel, CorridorLeg, Port, WeatherAlert, WeatherSnapshot
from app.integrations.weather.base import WeatherProviderError, WindObservation, WindReport
from app.integrations.weather.open_meteo import OpenMeteoProvider
from app.services.weather_predictor import (
    WeatherPredictor,
    WindThresholds,
    evaluate_level,
    forecast_peak,
)

THRESHOLDS = WindThresholds(
    watch_wind=10.0,
    warning_wind=13.8,
    warning_gust=15.0,
    critical_wind=17.0,
    critical_gust=21.0,
)


def _obs(speed: float, gust: float, hours_ahead: float = 0) -> WindObservation:
    from datetime import timedelta

    return WindObservation(
        wind_speed=speed,
        wind_gust=gust,
        wind_dir=180.0,
        ts=datetime.now(UTC) + timedelta(hours=hours_ahead),
    )


class FakeProvider:
    """Провайдер с заранее заданной погодой/прогнозом (или ошибкой)."""

    def __init__(self) -> None:
        self.observation: WindObservation | None = None
        self.forecast: list[WindObservation] = []
        self.error: Exception | None = None

    async def get_wind(self, lat: float, lon: float) -> WindReport:
        if self.error is not None:
            raise self.error
        assert self.observation is not None
        return WindReport(current=self.observation, forecast=self.forecast)


class FakeSink:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.error: Exception | None = None

    async def publish(self, text: str) -> None:
        if self.error is not None:
            raise self.error
        self.messages.append(text)


@pytest.fixture
async def port(session: AsyncSession) -> Port:
    port = Port(
        code="AKTAU",
        name="Актау",
        country="Казахстан",
        leg=CorridorLeg.caspian,
        lat=43.63,
        lon=51.25,
        is_weather_tracked=True,
    )
    session.add(port)
    await session.commit()
    return port


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def sink() -> FakeSink:
    return FakeSink()


@pytest.fixture
def predictor(
    session_factory: async_sessionmaker[AsyncSession],
    provider: FakeProvider,
    sink: FakeSink,
) -> WeatherPredictor:
    return WeatherPredictor(session_factory, provider, THRESHOLDS, sink)


# --- Пороги -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("speed", "gust", "expected"),
    [
        (5.0, 8.0, None),
        (9.9, 14.9, None),
        (10.0, 0.0, AlertLevel.watch),  # граница watch по ветру
        (12.0, 14.9, AlertLevel.watch),
        (13.8, 0.0, AlertLevel.warning),  # граница warning по ветру
        (0.0, 15.0, AlertLevel.warning),  # warning только по порывам
        (16.9, 20.9, AlertLevel.warning),
        (17.0, 0.0, AlertLevel.critical),  # граница critical по ветру
        (0.0, 21.0, AlertLevel.critical),  # critical только по порывам
        (25.0, 30.0, AlertLevel.critical),
    ],
)
def test_evaluate_level(speed: float, gust: float, expected: AlertLevel | None) -> None:
    assert evaluate_level(speed, gust, THRESHOLDS) is expected


# --- Жизненный цикл алертов --------------------------------------------------


async def _alerts(session: AsyncSession) -> list[WeatherAlert]:
    result = await session.execute(select(WeatherAlert).order_by(WeatherAlert.id))
    return list(result.scalars().all())


async def test_warning_opens_alert_and_publishes(
    predictor: WeatherPredictor,
    provider: FakeProvider,
    sink: FakeSink,
    session: AsyncSession,
    port: Port,
) -> None:
    provider.observation = _obs(15.0, 16.0)
    await predictor.poll_once()

    alerts = await _alerts(session)
    assert len(alerts) == 1
    assert alerts[0].level is AlertLevel.warning
    assert alerts[0].is_active is True
    assert len(sink.messages) == 1
    assert "Актау" in sink.messages[0]
    assert "15 м/с" in sink.messages[0]

    snapshots = (await session.execute(select(func.count(WeatherSnapshot.id)))).scalar_one()
    assert snapshots == 1


async def test_same_level_is_not_republished(
    predictor: WeatherPredictor,
    provider: FakeProvider,
    sink: FakeSink,
    session: AsyncSession,
    port: Port,
) -> None:
    provider.observation = _obs(15.0, 16.0)
    await predictor.poll_once()
    provider.observation = _obs(14.5, 16.5)  # всё ещё warning
    await predictor.poll_once()

    alerts = await _alerts(session)
    assert len(alerts) == 1  # антиспам: без дубликата
    assert len(sink.messages) == 1


async def test_escalation_to_critical_publishes(
    predictor: WeatherPredictor,
    provider: FakeProvider,
    sink: FakeSink,
    session: AsyncSession,
    port: Port,
) -> None:
    provider.observation = _obs(15.0, 16.0)
    await predictor.poll_once()
    provider.observation = _obs(18.0, 23.0)
    await predictor.poll_once()

    alerts = await _alerts(session)
    assert len(alerts) == 2
    assert alerts[0].is_active is False and alerts[0].closed_at is not None
    assert alerts[1].level is AlertLevel.critical and alerts[1].is_active is True
    assert len(sink.messages) == 2


async def test_deescalation_critical_to_warning_is_silent(
    predictor: WeatherPredictor,
    provider: FakeProvider,
    sink: FakeSink,
    session: AsyncSession,
    port: Port,
) -> None:
    provider.observation = _obs(18.0, 23.0)
    await predictor.poll_once()
    provider.observation = _obs(15.0, 16.0)
    await predictor.poll_once()

    alerts = await _alerts(session)
    assert len(alerts) == 2
    assert alerts[1].level is AlertLevel.warning and alerts[1].is_active is True
    assert len(sink.messages) == 1  # только исходный critical, понижение тихое


async def test_all_clear_published_when_wind_drops(
    predictor: WeatherPredictor,
    provider: FakeProvider,
    sink: FakeSink,
    session: AsyncSession,
    port: Port,
) -> None:
    provider.observation = _obs(15.0, 16.0)
    await predictor.poll_once()
    provider.observation = _obs(5.0, 7.0)
    await predictor.poll_once()

    alerts = await _alerts(session)
    assert len(alerts) == 1
    assert alerts[0].is_active is False
    assert len(sink.messages) == 2
    assert "отбой" in sink.messages[1].lower()


async def test_watch_is_tracked_but_silent(
    predictor: WeatherPredictor,
    provider: FakeProvider,
    sink: FakeSink,
    session: AsyncSession,
    port: Port,
) -> None:
    provider.observation = _obs(11.0, 12.0)
    await predictor.poll_once()
    provider.observation = _obs(5.0, 6.0)
    await predictor.poll_once()

    alerts = await _alerts(session)
    assert len(alerts) == 1
    assert alerts[0].level is AlertLevel.watch
    assert alerts[0].is_active is False  # закрыт при стихании
    assert sink.messages == []  # watch не публикуется


async def test_provider_error_does_not_crash_poll(
    predictor: WeatherPredictor,
    provider: FakeProvider,
    sink: FakeSink,
    session: AsyncSession,
    port: Port,
) -> None:
    provider.error = WeatherProviderError("boom")
    await predictor.poll_once()  # не должно бросить

    snapshots = (await session.execute(select(func.count(WeatherSnapshot.id)))).scalar_one()
    assert snapshots == 0
    assert sink.messages == []


async def test_publish_failure_does_not_lose_alert(
    predictor: WeatherPredictor,
    provider: FakeProvider,
    sink: FakeSink,
    session: AsyncSession,
    port: Port,
) -> None:
    sink.error = RuntimeError("telegram down")
    provider.observation = _obs(18.0, 23.0)
    await predictor.poll_once()  # не должно бросить

    alerts = await _alerts(session)
    assert len(alerts) == 1
    assert alerts[0].level is AlertLevel.critical


# --- Прогноз ------------------------------------------------------------------


def test_forecast_peak_picks_highest_level_first_hour() -> None:
    forecast = [
        _obs(8.0, 10.0, hours_ahead=1),
        _obs(15.0, 16.0, hours_ahead=6),  # warning
        _obs(18.0, 22.0, hours_ahead=12),  # critical — пик
        _obs(18.5, 23.0, hours_ahead=13),  # тоже critical, но позже
    ]
    peak = forecast_peak(forecast, THRESHOLDS)
    assert peak is not None
    level, hour = peak
    assert level is AlertLevel.critical
    assert hour.wind_speed == 18.0  # первый час достижения максимума


def test_forecast_peak_none_when_calm() -> None:
    assert forecast_peak([_obs(5.0, 7.0, hours_ahead=3)], THRESHOLDS) is None


async def test_forecast_driven_alert_published_in_advance(
    predictor: WeatherPredictor,
    provider: FakeProvider,
    sink: FakeSink,
    session: AsyncSession,
    port: Port,
) -> None:
    provider.observation = _obs(5.0, 7.0)  # сейчас штиль
    provider.forecast = [_obs(16.0, 19.0, hours_ahead=8)]  # шторм к вечеру
    await predictor.poll_once()

    alerts = await _alerts(session)
    assert len(alerts) == 1
    assert alerts[0].level is AlertLevel.warning
    assert "Прогноз" in alerts[0].message
    assert len(sink.messages) == 1
    assert "ожидается" in sink.messages[0]
    assert "усиление до 16 м/с" in sink.messages[0]


async def test_forecast_alert_not_reopened_while_forecast_holds(
    predictor: WeatherPredictor,
    provider: FakeProvider,
    sink: FakeSink,
    session: AsyncSession,
    port: Port,
) -> None:
    provider.observation = _obs(5.0, 7.0)
    provider.forecast = [_obs(16.0, 19.0, hours_ahead=8)]
    await predictor.poll_once()
    provider.forecast = [_obs(15.5, 18.0, hours_ahead=7)]  # всё ещё warning
    await predictor.poll_once()

    assert len(await _alerts(session)) == 1  # антиспам работает и для прогноза
    assert len(sink.messages) == 1


async def test_all_clear_when_forecast_calms_down(
    predictor: WeatherPredictor,
    provider: FakeProvider,
    sink: FakeSink,
    session: AsyncSession,
    port: Port,
) -> None:
    provider.observation = _obs(5.0, 7.0)
    provider.forecast = [_obs(16.0, 19.0, hours_ahead=8)]
    await predictor.poll_once()
    provider.forecast = [_obs(6.0, 8.0, hours_ahead=8)]  # прогноз улучшился
    await predictor.poll_once()

    alerts = await _alerts(session)
    assert alerts[0].is_active is False
    assert len(sink.messages) == 2
    assert "отбой" in sink.messages[1].lower()


# --- Парсер Open-Meteo --------------------------------------------------------


async def test_open_meteo_parses_response_with_forecast() -> None:
    payload = {
        "current": {
            "time": "2026-07-17T09:40",
            "wind_speed_10m": 15.2,
            "wind_gusts_10m": 19.4,
            "wind_direction_10m": 210,
        },
        "hourly": {
            "time": ["2026-07-17T09:00", "2026-07-17T10:00", "2026-07-17T11:00"],
            "wind_speed_10m": [14.0, 16.5, None],  # null в хвосте — пропускается
            "wind_gusts_10m": [17.0, 20.1, None],
            "wind_direction_10m": [200, 215, None],
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["wind_speed_unit"] == "ms"
        assert "hourly" in request.url.params
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenMeteoProvider(client=client)
    report = await provider.get_wind(43.63, 51.25)

    assert report.current.wind_speed == 15.2
    assert report.current.ts == datetime(2026, 7, 17, 9, 40, tzinfo=UTC)
    assert report.current.raw == payload
    # 09:00 — в прошлом (до current.ts), null-час отброшен → остаётся 10:00
    assert len(report.forecast) == 1
    assert report.forecast[0].wind_speed == 16.5
    assert report.forecast[0].ts == datetime(2026, 7, 17, 10, 0, tzinfo=UTC)
    await client.aclose()


async def test_open_meteo_malformed_response_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenMeteoProvider(client=client)
    with pytest.raises(WeatherProviderError):
        await provider.get_wind(43.63, 51.25)
    await client.aclose()
