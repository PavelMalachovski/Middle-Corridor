"""Провайдер погоды Open-Meteo (бесплатный, без ключа).

https://open-meteo.com/en/docs — запрашиваем текущий ветер на высоте 10 м
в м/с. Ретраи с экспоненциальным backoff на сетевые ошибки и 429/5xx.
"""

import asyncio
from datetime import UTC, datetime

import httpx
import structlog

from app.integrations.weather.base import WeatherProviderError, WindObservation

logger = structlog.get_logger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class OpenMeteoProvider:
    """Реализация WeatherProvider на Open-Meteo."""

    def __init__(self, client: httpx.AsyncClient | None = None, retries: int = 3) -> None:
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(10.0))
        self._retries = retries

    async def get_current_wind(self, lat: float, lon: float) -> WindObservation:
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "wind_speed_10m,wind_gusts_10m,wind_direction_10m",
            "wind_speed_unit": "ms",
            "timezone": "UTC",
        }
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
            return self._parse(response.json())
        raise WeatherProviderError("Open-Meteo недоступен") from last_error

    @staticmethod
    def _parse(data: dict) -> WindObservation:
        try:
            current = data["current"]
            ts = datetime.fromisoformat(current["time"]).replace(tzinfo=UTC)
            return WindObservation(
                wind_speed=float(current["wind_speed_10m"]),
                wind_gust=float(current["wind_gusts_10m"]),
                wind_dir=float(current["wind_direction_10m"]),
                ts=ts,
                raw=data,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise WeatherProviderError(f"Некорректный ответ Open-Meteo: {exc}") from exc

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
