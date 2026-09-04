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
        # Пустая переменная = не задана (берём default). Иначе Vercel, импортируя
        # .env.example с пустыми значениями, роняет Settings() на int/float/bool.
        env_ignore_empty=True,
    )

    # Telegram
    bot_token: str = ""
    channel_id: str = ""  # -100... или @username; пусто = публикация в канал выключена
    admin_user_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)
    # Публичный HTTPS-адрес приложения (https://xxx.up.railway.app).
    # Задан = бот работает через вебхук; пусто = long polling (локальная разработка)
    bot_webhook_url: str = ""
    bot_webhook_secret: str = ""  # пусто = выводится из токена

    # Database
    database_url: str = "postgresql+asyncpg://mc:mc@localhost:5433/mc_status"

    # AIS
    aisstream_api_key: str = ""
    vesselapi_api_key: str = ""
    vesselapi_webhook_secret: str = ""  # пусто = вебхук выключен
    # bbox "lat_min,lon_min,lat_max,lon_max" — уточняются без кода
    ais_bbox_caspian: str = "36.5,47.0,47.0,54.5"
    ais_bbox_black_sea: str = "41.0,40.5,43.5,42.5"
    ais_min_save_interval_minutes: int = 5  # троттлинг записи позиций

    # LLM (перевод/суммаризация новостей); пустой ключ = перевод выключен
    anthropic_api_key: str = ""
    llm_model: str = "claude-opus-4-8"

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
    scheduler_enabled: bool = False  # false = погода/новости только по команде админа
    news_sources: Annotated[list[str], NoDecode] = Field(default_factory=list)
    weather_poll_minutes: int = 45
    news_poll_minutes: int = 60
    news_max_per_run: int = 3  # троттлинг публикаций за прогон
    news_max_age_days: int = 7  # старше — в архив без публикации

    # Web-карта (фаза 2). MOCK_DATA=true — /api/v1 отдаёт синтетику без БД
    # и внешних API; MOCK_TIME_SCALE=60 — час мок-времени за минуту (демо).
    mock_data: bool = False
    mock_time_scale: float = 1.0
    web_dist_dir: str = "web/dist"  # собранный фронт; нет каталога = не раздаём
    # Origin'ы фронта, живущего на другом домене (например, Vercel при бэкенде
    # на Railway), через запятую. Пусто = CORS выключен (фронт раздаёт сам API).
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

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

    @field_validator("news_sources", "cors_origins", mode="before")
    @classmethod
    def _parse_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
