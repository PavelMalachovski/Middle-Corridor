"""Единая точка публикации в публичный канал."""

import structlog
from aiogram import Bot

logger = structlog.get_logger(__name__)


class ChannelPublisher:
    """Реализация MessageSink поверх Telegram-канала."""

    def __init__(self, bot: Bot, channel_id: str) -> None:
        self._bot = bot
        self._channel_id = channel_id

    async def publish(self, text: str) -> None:
        if not self._channel_id:
            logger.warning(
                "channel_not_configured", detail="CHANNEL_ID пуст — публикация пропущена"
            )
            return
        await self._bot.send_message(chat_id=self._channel_id, text=text)
        logger.info("channel_message_sent", length=len(text))
