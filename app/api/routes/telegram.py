"""Telegram-вебхук: приём апдейтов вместо long polling.

Включается, когда задан BOT_WEBHOOK_URL. Telegram шлёт секрет в заголовке
X-Telegram-Bot-Api-Secret-Token — сверяем с нашим.

Апдейт обрабатывается в фоне, ответ 200 — сразу: иначе ошибка хендлера (500)
или долгая команда вроде /poll_news (дольше таймаута Telegram) заставляют
Telegram слать тот же апдейт повторно.
"""

import asyncio
import hmac

import structlog
from aiogram.types import Update
from fastapi import APIRouter, Header, HTTPException, Request

logger = structlog.get_logger(__name__)

router = APIRouter()

TELEGRAM_WEBHOOK_PATH = "/telegram/webhook"

# Сильные ссылки на фоновые задачи: event loop держит только слабые
_background: set[asyncio.Task[object]] = set()


def _secret_ok(given: str | None, expected: str) -> bool:
    if not expected or given is None:
        return False
    return hmac.compare_digest(given.encode(), expected.encode())


def _on_update_done(task: asyncio.Task[object]) -> None:
    _background.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error("telegram_update_failed", task=task.get_name(), exc_info=exc)


@router.post(TELEGRAM_WEBHOOK_PATH)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    bot = request.app.state.bot
    dispatcher = request.app.state.dispatcher
    secret = request.app.state.telegram_webhook_secret
    if not _secret_ok(x_telegram_bot_api_secret_token, secret):
        raise HTTPException(status_code=403, detail="invalid secret token")
    if bot is None or dispatcher is None:
        raise HTTPException(status_code=503, detail="bot is not running")

    update = Update.model_validate(await request.json(), context={"bot": bot})
    task = asyncio.create_task(
        dispatcher.feed_update(bot, update), name=f"tg-update-{update.update_id}"
    )
    _background.add(task)
    task.add_done_callback(_on_update_done)
    return {"ok": True}
