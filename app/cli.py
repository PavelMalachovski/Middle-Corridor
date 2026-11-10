"""Команды админа платформы: python -m app.cli ..."""

import argparse
import asyncio
from datetime import UTC, datetime

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db.models import OrgKind, Role
from app.services.accounts.errors import AccountsError
from app.services.accounts.mail import EmailSender, LogEmailSender, ResendEmailSender
from app.services.accounts.orgs import OrgService


def mask(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m app.cli")
    p.add_argument("--database-url", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("admin", help="сделать пользователя админом платформы")
    a.add_argument("--email", required=True)
    org = sub.add_parser("org")
    osub = org.add_subparsers(dest="sub", required=True)
    c = osub.add_parser("create")
    c.add_argument("--kind", required=True, choices=[k.value for k in OrgKind])
    c.add_argument("--name", required=True)
    link = osub.add_parser("link")
    link.add_argument("--forwarder", type=int, required=True)
    link.add_argument("--client", type=int, required=True)
    inv = sub.add_parser("invite")
    inv.add_argument("--org", type=int, required=True)
    inv.add_argument("--email", required=True)
    inv.add_argument("--role", required=True, choices=[r.value for r in Role])
    inv.add_argument("--nodes", default="")
    user = sub.add_parser("user")
    usub = user.add_subparsers(dest="sub", required=True)
    d = usub.add_parser("disable")
    d.add_argument("--email", required=True)
    return p


async def _run(args: argparse.Namespace) -> None:
    settings = get_settings()
    engine = create_async_engine(args.database_url or settings.database_url)
    client: httpx.AsyncClient | None = None
    mail: EmailSender = LogEmailSender()
    if settings.email_provider == "resend":
        client = httpx.AsyncClient(timeout=10)
        mail = ResendEmailSender(settings.email_api_key, settings.email_from, client)
    svc = OrgService(
        async_sessionmaker(engine, expire_on_commit=False), mail, lambda: datetime.now(UTC)
    )
    try:
        if args.cmd == "admin":
            user = await svc.set_platform_admin(args.email)
            print(f"admin: {mask(user.email)}")
        elif args.cmd == "org" and args.sub == "create":
            org = await svc.create_org(None, args.name, OrgKind(args.kind))
            print(org.id)
        elif args.cmd == "org" and args.sub == "link":
            await svc.link(None, args.forwarder, args.client)
            print("linked")
        elif args.cmd == "invite":
            nodes = [n.strip().upper() for n in args.nodes.split(",") if n.strip()]
            inv = await svc.invite(None, args.org, args.email, Role(args.role), nodes)
            print(f"invited: {mask(inv.email)}")
        elif args.cmd == "user" and args.sub == "disable":
            await svc.disable_user(args.email)
            print(f"disabled: {mask(args.email)}")
    finally:
        if client is not None:
            await client.aclose()
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        asyncio.run(_run(args))
    except (ValueError, AccountsError) as exc:
        print(f"error: {exc or type(exc).__name__}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
