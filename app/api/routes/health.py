"""Liveness/readiness проверка."""

from fastapi import APIRouter, Request
from sqlalchemy import text

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict[str, object]:
    """Liveness всегда ok; db=true, если БД доступна."""
    engine = request.app.state.engine
    db_ok = False
    if engine is not None:
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            db_ok = True
        except Exception:  # noqa: BLE001 — health не должен падать из-за БД
            db_ok = False
    return {"status": "ok", "db": db_ok}
