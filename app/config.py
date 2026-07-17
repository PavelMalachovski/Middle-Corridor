"""Конфигурация приложения.

Все параметры читаются из переменных окружения (или .env для локальной
разработки). Никаких секретов в коде.
"""

from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    bot_token: str = ""
    channel_id: str = ""  # -100... или @username; пусто = публикация в канал выключена
    admin_user_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)

    # Database
    database_url: str = "postgresql+asyncpg://mc:mc@localhost:5433/mc_status"

    # AIS
    aisstream_api_key: str = ""
    vesselapi_api_key: str = ""

    # Пороги ветра (м/с) для предиктора остановки портов.
    # Стартовые значения: их нужно калибровать по фактическим остановкам портов
    # после накопления реальных данных — это ядро точности продукта.
    weather_watch_wind: float = 10.0
    weather_warning_wind: float = 13.8
    weather_warning_gust: float = 15.0
    weather_critical_wind: float = 17.0
    weather_critical_gust: float = 21.0

    # Behaviour
    auto_publish_reports: bool = False
    news_sources: Annotated[list[str], NoDecode] = Field(default_factory=list)
    weather_poll_minutes: int = 45
    news_poll_minutes: int = 60
    news_max_per_run: int = 3  # троттлинг публикаций за прогон
    news_max_age_days: int = 7  # старше — в архив без публикации

    # Runtime
    log_level: str = "INFO"
    env: str = "production"
    port: int = 8000

    @field_validator("admin_user_ids", mode="before")
    @classmethod
    def _parse_admin_ids(cls, value: object) -> object:
        if isinstance(value, str):
            return [int(part) for part in value.replace(" ", "").split(",") if part]
        return value

    @field_validator("news_sources", mode="before")
    @classmethod
    def _parse_news_sources(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
