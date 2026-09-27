"""Интерфейс источника новостей."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from urllib.parse import urlparse

# Лимиты колонок news_items (app/db/models.py): длиннее — Postgres отвергнет вставку
MAX_URL_LEN = 1024
MAX_EXTERNAL_ID_LEN = 256
MAX_TITLE_LEN = 512


def is_acceptable_url(url: str) -> bool:
    """Ссылка годится для БД и для <a href> в канале: только http(s), влезает в колонку."""
    return len(url) <= MAX_URL_LEN and urlparse(url).scheme in ("http", "https")


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
