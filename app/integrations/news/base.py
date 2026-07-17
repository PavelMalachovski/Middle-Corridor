"""Интерфейс источника новостей."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class NewsEntry:
    """Новость из внешнего источника (до сохранения в БД)."""

    source: str  # человекочитаемое имя источника (домен)
    url: str
    title: str
    external_id: str | None = None
    summary: str | None = None
    published_at: datetime | None = None


class NewsProviderError(RuntimeError):
    """Источник новостей недоступен или вернул некорректный ответ."""


class NewsProvider(Protocol):
    async def fetch(self, feed_url: str) -> list[NewsEntry]: ...
