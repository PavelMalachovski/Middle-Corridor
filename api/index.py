"""Vercel: FastAPI как serverless-функция — JSON-API карты и /health.

Статика фронта (web/dist) раздаётся CDN Vercel, все /api/* и /health
переписываются сюда (см. vercel.json). Бот, AIS-воркер и планировщик здесь
не живут — им нужен постоянный процесс (Railway, см. app/main.py).

Режимы:
- MOCK_DATA=true (демо) — синтетика без БД и внешних API;
- DATABASE_URL задан (Neon/Supabase, лучше через pooler) — боевые порты,
  суда, новости и снимки поля ветра из БД (ветер при пустой таблице берётся
  у Open-Meteo по запросу, WIND_GRID_LAZY_REFRESH); отправки пока без источника.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # корень репо → import app

from app.api.main import create_app  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db.base import create_engine, create_session_factory  # noqa: E402
from app.main import build_map_service  # noqa: E402

settings = get_settings()
engine = None if settings.mock_data else create_engine(settings.database_url)
session_factory = create_session_factory(engine) if engine is not None else None

app = create_app(
    engine=engine,
    settings=settings,
    map_service=build_map_service(settings, session_factory),
)
