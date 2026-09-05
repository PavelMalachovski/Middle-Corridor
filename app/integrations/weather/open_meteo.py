"""Провайдер погоды Open-Meteo (бесплатный, без ключа).

https://open-meteo.com/en/docs — текущий ветер на высоте 10 м плюс
почасовой прогноз на forecast_hours вперёд, всё в м/с. Ретраи с
экспоненциальным backoff на 429/5xx и сетевые ошибки.
"""

import asyncio
from datetime import UTC, datetime

import httpx
import structlog

from app.integrations.weather.base import (
    GridPointForecast,
    WeatherProviderError,
    WindObservation,
    WindReport,
)

logger = structlog.get_logger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_WIND_VARS = "wind_speed_10m,wind_gusts_10m,wind_direction_10m"
GRID_BATCH = 100  # точек сетки в одном запросе


class OpenMeteoProvider:
    """Реализация WeatherProvider на Open-Meteo."""

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        retries: int = 3,
        forecast_hours: int = 24,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(10.0))
        self._retries = retries
        self._forecast_hours = forecast_hours

    async def get_wind(self, lat: float, lon: float) -> WindReport:
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": _WIND_VARS,
            "hourly": _WIND_VARS,
            # +1 час, чтобы после отсечения прошедшего часа остался полный горизонт
            "forecast_hours": self._forecast_hours + 1,
            "wind_speed_unit": "ms",
            "timezone": "UTC",
        }
        return self._parse(await self._request(params))

    async def get_wind_grid(
        self, points: list[tuple[float, float]], forecast_hours: int
    ) -> list[GridPointForecast]:
        """Почасовой прогноз в узлах сетки — батчами по GRID_BATCH точек за запрос.

        Open-Meteo принимает списки координат через запятую и отвечает
        массивом объектов в том же порядке; каждая точка считается отдельным
        вызовом в лимитах, поэтому сетку держим редкой, а обновление — нечастым.
        """
        out: list[GridPointForecast] = []
        for start in range(0, len(points), GRID_BATCH):
            batch = points[start : start + GRID_BATCH]
            params = {
                "latitude": ",".join(f"{lat:.3f}" for lat, _ in batch),
                "longitude": ",".join(f"{lon:.3f}" for _, lon in batch),
                "hourly": _WIND_VARS,
                "forecast_hours": forecast_hours,
                "wind_speed_unit": "ms",
                "timezone": "UTC",
            }
            data = await self._request(params)
            items = data if isinstance(data, list) else [data]
            if len(items) != len(batch):
                raise WeatherProviderError(
                    f"Open-Meteo вернул {len(items)} точек вместо {len(batch)}"
                )
            for (lat, lon), item in zip(batch, items, strict=True):
                out.append(GridPointForecast(lat=lat, lon=lon, hours=self._parse_hourly(item)))
        return out

    async def _request(self, params: dict) -> dict | list:
        last_error: Exception | None = None
        for attempt in range(self._retries):
            if attempt:
                await asyncio.sleep(min(2**attempt, 8))
            try:
                response = await self._client.get(OPEN_METEO_URL, params=params)
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning("open_meteo_request_failed", attempt=attempt, error=str(exc))
                continue
            if response.status_code in _RETRYABLE_STATUS:
                last_error = WeatherProviderError(f"HTTP {response.status_code}")
                logger.warning("open_meteo_retryable_status", status=response.status_code)
                continue
            if response.status_code != 200:
                raise WeatherProviderError(f"HTTP {response.status_code}: {response.text[:200]}")
            return response.json()
        raise WeatherProviderError("Open-Meteo недоступен") from last_error

    @classmethod
    def _parse_hourly(cls, item: dict) -> list[WindObservation]:
        """Почасовые ряды одной точки; null-хвост прогноза отбрасывается."""
        try:
            hourly = item.get("hourly") or {}
            out: list[WindObservation] = []
            for time_raw, speed, gust, direction in zip(
                hourly.get("time", []),
                hourly.get("wind_speed_10m", []),
                hourly.get("wind_gusts_10m", []),
                hourly.get("wind_direction_10m", []),
                strict=False,
            ):
                if speed is None or gust is None:
                    continue
                out.append(
                    WindObservation(
                        wind_speed=float(speed),
                        wind_gust=float(gust),
                        wind_dir=float(direction) if direction is not None else 0.0,
                        ts=cls._parse_ts(time_raw),
                    )
                )
            return out
        except (KeyError, TypeError, ValueError) as exc:
            raise WeatherProviderError(f"Некорректный ответ Open-Meteo: {exc}") from exc

    @staticmethod
    def _parse_ts(raw: str) -> datetime:
        return datetime.fromisoformat(raw).replace(tzinfo=UTC)

    @classmethod
    def _parse(cls, data: dict) -> WindReport:
        try:
            current_raw = data["current"]
            current = WindObservation(
                wind_speed=float(current_raw["wind_speed_10m"]),
                wind_gust=float(current_raw["wind_gusts_10m"]),
                wind_dir=float(current_raw["wind_direction_10m"]),
                ts=cls._parse_ts(current_raw["time"]),
                raw=data,
            )
            forecast: list[WindObservation] = []
            hourly = data.get("hourly") or {}
            for time_raw, speed, gust, direction in zip(
                hourly.get("time", []),
                hourly.get("wind_speed_10m", []),
                hourly.get("wind_gusts_10m", []),
                hourly.get("wind_direction_10m", []),
                strict=False,
            ):
                if speed is None or gust is None:
                    continue  # у Open-Meteo бывают null в хвосте прогноза
                ts = cls._parse_ts(time_raw)
                if ts <= current.ts:
                    continue  # прошедшие часы не интересны
                forecast.append(
                    WindObservation(
                        wind_speed=float(speed),
                        wind_gust=float(gust),
                        wind_dir=float(direction) if direction is not None else 0.0,
                        ts=ts,
                    )
                )
            return WindReport(current=current, forecast=forecast)
        except (KeyError, TypeError, ValueError) as exc:
            raise WeatherProviderError(f"Некорректный ответ Open-Meteo: {exc}") from exc

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
