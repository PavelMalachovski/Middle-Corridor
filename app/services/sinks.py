"""Интерфейс публикации сообщений.

Сервисы не знают про Telegram: они публикуют через MessageSink,
реализация — app.bot.publisher.ChannelPublisher.
"""

from typing import Protocol


class MessageSink(Protocol):
    async def publish(self, text: str) -> None: ...
