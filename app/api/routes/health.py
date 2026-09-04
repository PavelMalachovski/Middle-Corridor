"""Liveness/readiness проверка."""

from datetime import UTC, datetime

from fastapi import APIRouter, Request
from sqlalchemy import text

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict[str, object]:
    """Liveness всегда ok; db=true, если БД доступна; возраст последнего AIS-сообщения.

    mock=true — API карты отдаёт синтетику (MOCK_DATA); с mock=false и db=false
    /api/v1 ответит 503 — самый частый случай на демо-деплое без Postgres.
    """
    engine = request.app.state.engine
    db_ok = False
    if engine is not None:
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            db_ok = True
        except Exception:  # noqa: BLE001 — health не должен падать из-за БД
            db_ok = False

    ais_age_s: int | None = None
    worker = getattr(request.app.state, "ais_worker", None)
    if worker is not None and worker.last_message_at is not None:
        ais_age_s = int((datetime.now(UTC) - worker.last_message_at).total_seconds())

    return {
        "status": "ok",
        "db": db_ok,
        "mock": bool(request.app.state.settings.mock_data),
        "ais_last_message_age_s": ais_age_s,
    }
