"""Telegram-вебхук: приём апдейтов вместо long polling.

Включается, когда задан BOT_WEBHOOK_URL. Telegram шлёт секрет в заголовке
X-Telegram-Bot-Api-Secret-Token — сверяем с нашим.
"""

import structlog
from aiogram.types import Update
from fastapi import APIRouter, Header, HTTPException, Request

logger = structlog.get_logger(__name__)

router = APIRouter()

TELEGRAM_WEBHOOK_PATH = "/telegram/webhook"


@router.post(TELEGRAM_WEBHOOK_PATH)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    bot = request.app.state.bot
    dispatcher = request.app.state.dispatcher
    secret = request.app.state.telegram_webhook_secret
    if not secret or x_telegram_bot_api_secret_token != secret:
        raise HTTPException(status_code=403, detail="invalid secret token")
    if bot is None or dispatcher is None:
        raise HTTPException(status_code=503, detail="bot is not running")

    update = Update.model_validate(await request.json(), context={"bot": bot})
    await dispatcher.feed_update(bot, update)
    return {"ok": True}
