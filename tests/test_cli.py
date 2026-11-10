import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from app.cli import main
from app.db.base import Base
from app.db.models import AuthSession, Invitation, Organization, User


@pytest.fixture
def db_url(tmp_path) -> str:
    url = f"sqlite+aiosqlite:///{tmp_path / 'cli.db'}"

    async def create() -> None:
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(create())
    return url


def query(url: str, stmt):
    async def run():
        engine = create_async_engine(url)
        async with engine.connect() as conn:
            rows = (await conn.execute(stmt)).all()
        await engine.dispose()
        return rows

    return asyncio.run(run())


def test_cli_bootstrap(db_url, capsys):
    base = ["--database-url", db_url]
    assert main([*base, "admin", "--email", "boss@firm.kz"]) == 0
    assert main([*base, "org", "create", "--kind", "forwarder", "--name", "Fwd"]) == 0
    out = capsys.readouterr().out
    org_id = int(out.strip().splitlines()[-1])
    assert (
        main(
            [
                *base,
                "invite",
                "--org",
                str(org_id),
                "--email",
                "agent@firm.kz",
                "--role",
                "agent",
                "--nodes",
                "AKTAU,POTI",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "agent@firm.kz" not in out and "a***@firm.kz" in out
    inv = query(db_url, select(Invitation))
    assert len(inv) == 1
    assert query(db_url, select(Organization.name)) == [("Fwd",)]


def test_cli_user_disable_revokes_sessions(db_url):
    base = ["--database-url", db_url]
    main([*base, "admin", "--email", "boss@firm.kz"])

    async def add_session() -> None:
        from datetime import UTC, datetime

        from sqlalchemy.ext.asyncio import async_sessionmaker

        engine = create_async_engine(db_url)
        async with async_sessionmaker(engine)() as s:
            uid = (await s.execute(select(User.id))).scalar_one()
            s.add(
                AuthSession(
                    user_id=uid, token_hash="h", expires_at=datetime(2030, 1, 1, tzinfo=UTC)
                )
            )
            await s.commit()
        await engine.dispose()

    asyncio.run(add_session())
    assert main([*base, "user", "disable", "--email", "boss@firm.kz"]) == 0
    assert query(db_url, select(User.disabled_at))[0][0] is not None
    assert query(db_url, select(AuthSession.revoked_at))[0][0] is not None
