"""REST-клиент VesselAPI — резервный источник позиций и событий портов.

ВНИМАНИЕ: базовый URL и форма ответов зависят от тарифа/версии VesselAPI —
сверить с документацией аккаунта перед боевым использованием. Клиент
изолирован за интерфейсом, менять безопасно. События портов принимаются
пуш-вебхуком (api/routes/webhooks.py), этот клиент — pull-резерв.
"""

from datetime import UTC, datetime

import httpx
import structlog

from app.integrations.ais.base import AISPosition, AISProviderError

logger = structlog.get_logger(__name__)

DEFAULT_BASE_URL = "https://api.vesselapi.com/v1"


class VesselApiClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=httpx.Timeout(15.0))

    async def get_position(self, mmsi: int) -> AISPosition | None:
        """Последняя известная позиция судна; None, если судно не найдено."""
        try:
            response = await self._client.get(
                f"/vessels/{mmsi}/position", headers={"Authorization": f"Bearer {self._api_key}"}
            )
        except httpx.HTTPError as exc:
            raise AISProviderError(f"VesselAPI недоступен: {exc}") from exc
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise AISProviderError(f"VesselAPI HTTP {response.status_code}")
        data = response.json()
        try:
            return AISPosition(
                mmsi=mmsi,
                lat=float(data["latitude"]),
                lon=float(data["longitude"]),
                sog=float(data["speed"]) if data.get("speed") is not None else None,
                cog=float(data["course"]) if data.get("course") is not None else None,
                nav_status=data.get("status"),
                ts=(
                    datetime.fromisoformat(data["timestamp"])
                    if data.get("timestamp")
                    else datetime.now(UTC)
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AISProviderError(f"Некорректный ответ VesselAPI: {exc}") from exc

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
