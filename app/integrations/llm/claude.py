"""Перевод и суммаризация новостей через Claude API (официальный SDK).

Англоязычные новости перед публикацией в канал переводятся на русский и
сжимаются до 2–3 предложений. Структурированный вывод через messages.parse —
ответ гарантированно валидируется схемой.
"""

import structlog
from anthropic import AsyncAnthropic
from pydantic import BaseModel

logger = structlog.get_logger(__name__)

_SYSTEM_PROMPT = (
    "Ты — редактор русскоязычного Telegram-канала об оперативной обстановке на "
    "Среднем коридоре (TITR): логистика Китай—Казахстан—Каспий—Кавказ—Европа. "
    "Переведи новость на русский. Заголовок — краткий и информативный. "
    "Описание сожми до 2–3 предложений, сохранив все цифры, даты, названия "
    "компаний и портов. Без воды и оценок. Если описания нет — верни только заголовок."
)


class NewsTranslation(BaseModel):
    title_ru: str
    summary_ru: str | None = None


class ClaudeNewsTranslator:
    def __init__(self, api_key: str, model: str = "claude-opus-4-8") -> None:
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    async def translate(self, title: str, summary: str | None) -> tuple[str, str | None]:
        """Возвращает (title_ru, summary_ru). Исключения пробрасываются наверх."""
        user_text = f"Заголовок: {title}"
        if summary:
            user_text += f"\n\nОписание: {summary}"

        response = await self._client.messages.parse(
            model=self._model,
            max_tokens=1024,  # переводы короткие
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_text}],
            output_format=NewsTranslation,
        )
        translation = response.parsed_output
        logger.info("news_translated", model=self._model, title=translation.title_ru[:80])
        return translation.title_ru, translation.summary_ru

    async def aclose(self) -> None:
        await self._client.close()
