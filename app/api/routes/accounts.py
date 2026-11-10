"""API аккаунтов: вход по коду, профиль, компании, мои грузы, события.

Только при `settings.accounts_enabled` (иначе каждый роут — 404, см. `deps.accounts`).
Ошибки сервисов: нет прав / нет объекта — 404 `not_found` (не 403);
`ValueError(code)` с кодом `[a-z_]+` — 422 `{"detail": code}`, прочие ValueError — 500.
В логах — id, не e-mail и не токен.

POST /api/v1/auth/code {email}                 → 202 всегда (письмо — в фоне)
POST /api/v1/auth/verify {email, code, device_name} → {token, me} | 401
POST /api/v1/auth/logout                       → 204
GET|PATCH /api/v1/me, POST /api/v1/me/devices
GET /api/v1/orgs/{id}/members|clients, POST …/invitations, DELETE …/members/{user_id}
POST /api/v1/admin/orgs, …/{id}/links, …/{id}/invitations (только платформа)
GET|POST /api/v1/my/shipments, GET|PATCH …/{ref}, POST …/{ref}/share|archive,
GET|POST …/{ref}/events, PUT …/{ref}/subscription
"""

import re
from collections.abc import Awaitable, Callable
from typing import Annotated

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import ValidationError

from app.api.deps import (
    AccountsServices,
    Caller,
    accounts,
    client_ip,
    current_caller,
    current_principal,
)
from app.api.routes.accounts_schemas import (
    EMAIL_MAX,
    PATCH_NULLABLE,
    CodeIn,
    DeviceIn,
    EventIn,
    EventOut,
    InviteIn,
    InviteOut,
    LinkIn,
    MemberOut,
    MembershipOut,
    MeOut,
    MePatch,
    MyShipment,
    OrgIn,
    OrgOut,
    ShareIn,
    ShipmentIn,
    ShipmentPatch,
    StatusOut,
    SubscriptionIn,
    VerifyIn,
    VerifyOut,
)
from app.services.accounts.access import Principal
from app.services.accounts.auth import AuthService
from app.services.accounts.errors import AccountsError, InvitationMailFailed
from app.services.accounts.events import EventView
from app.services.accounts.views import MyShipmentView, Profile, my_shipment, my_shipments

logger = structlog.get_logger(__name__)


_ERROR_CODE = re.compile(r"[a-z_]+")


class AccountsRoute(APIRoute):
    """Единое отображение ошибок сервисов аккаунтов в HTTP."""

    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        handler = super().get_route_handler()

        async def route(request: Request) -> Response:
            try:
                return await handler(request)
            except AccountsError:
                return JSONResponse({"detail": "not_found"}, status_code=404)
            except ValidationError:
                raise
            except ValueError as exc:
                if not _ERROR_CODE.fullmatch(str(exc)):
                    # не код сервиса — ошибка программы; текст может нести данные
                    logger.error("unexpected_value_error", error=type(exc).__name__)
                    raise
                return JSONResponse({"detail": str(exc)}, status_code=422)

        return route


router = APIRouter(prefix="/api/v1", route_class=AccountsRoute, dependencies=[Depends(accounts)])

Services = Annotated[AccountsServices, Depends(accounts)]
Actor = Annotated[Principal, Depends(current_principal)]
CurrentCaller = Annotated[Caller, Depends(current_caller)]


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="not_found")


def _platform(actor: Principal) -> Principal:
    if not actor.is_platform_admin:
        raise _not_found()
    return actor


def _me(profile: Profile) -> MeOut:
    user = profile.user
    return MeOut(
        id=user.id,
        email=user.email,
        name=user.name,
        locale=user.locale,
        is_platform_admin=user.is_platform_admin,
        memberships=[MembershipOut(**vars(m)) for m in profile.memberships],
    )


def _my(view: MyShipmentView) -> MyShipment:
    return MyShipment(**vars(view))


def _event(view: EventView) -> EventOut:
    e = view.row
    return EventOut(
        id=e.id,
        kind=e.kind,
        node_code=e.node_code,
        occurred_at=e.occurred_at,
        hold_code=e.hold_code,
        note=e.note,
        vessel=e.vessel,
        source=e.source,
        created_by=e.created_by,
        supersedes_id=e.supersedes_id,
        created_at=e.created_at,
        superseded=view.superseded,
    )


# --- вход ------------------------------------------------------------------


async def _send_code(auth: AuthService, email: str, ip: str) -> None:
    try:
        await auth.request_code(email, ip)
    except Exception as exc:  # без трассы: в параметрах SQL был бы адрес
        logger.error("login_code_failed", error=type(exc).__name__)


@router.post("/auth/code", status_code=202, response_model=StatusOut)
async def request_code(
    body: CodeIn, request: Request, background: BackgroundTasks, services: Services
) -> StatusOut:
    """Ответ уходит до любой работы с базой и почтой — по времени известный адрес
    не отличить от неизвестного; кривой адрес — тот же 202."""
    if "@" in body.email and len(body.email) <= EMAIL_MAX:
        background.add_task(_send_code, services.auth, body.email, client_ip(request))
    return StatusOut(status="sent")


@router.post("/auth/verify", response_model=VerifyOut)
async def verify(body: VerifyIn, request: Request, services: Services) -> VerifyOut:
    result = await services.auth.verify(body.email, body.code, body.device_name, client_ip(request))
    if result is None:
        raise HTTPException(status_code=401, detail="invalid_code")
    token, user = result
    logger.info("login_ok", user_id=user.id)
    return VerifyOut(token=token, me=_me(await services.profile.get(user.id)))


@router.post("/auth/logout", status_code=204)
async def logout(caller: CurrentCaller, services: Services) -> Response:
    await services.auth.logout(caller.token)
    return Response(status_code=204)


# --- профиль ---------------------------------------------------------------


@router.get("/me", response_model=MeOut)
async def get_me(caller: CurrentCaller, services: Services) -> MeOut:
    return _me(await services.profile.get(caller.user.id))


@router.patch("/me", response_model=MeOut)
async def patch_me(body: MePatch, caller: CurrentCaller, services: Services) -> MeOut:
    return _me(await services.profile.update(caller.user.id, name=body.name, locale=body.locale))


@router.post("/me/devices", status_code=204)
async def register_device(body: DeviceIn, caller: CurrentCaller, services: Services) -> Response:
    await services.notifier.register_device(caller.user.id, body.apns_token, body.environment)
    return Response(status_code=204)


# --- компании --------------------------------------------------------------


@router.get("/orgs/{org_id}/members", response_model=list[MemberOut])
async def members(org_id: int, actor: Actor, services: Services) -> list[MemberOut]:
    rows = await services.orgs.members_with_users(actor, org_id)
    return [
        MemberOut(
            user_id=u.id, email=u.email, name=u.name, role=m.role, node_codes=list(m.node_codes)
        )
        for m, u in rows
    ]


async def _invite(
    services: AccountsServices, actor: Principal, org_id: int, body: InviteIn
) -> InviteOut:
    try:
        inv = await services.orgs.invite(actor, org_id, body.email, body.role, body.node_codes)
    except InvitationMailFailed as exc:
        return InviteOut(invitation_id=exc.invitation_id, mail="failed")
    logger.info("invitation_created", invitation_id=inv.id, org_id=org_id, by=actor.user_id)
    return InviteOut(invitation_id=inv.id, mail="sent")


@router.post("/orgs/{org_id}/invitations", status_code=201, response_model=InviteOut)
async def invite(org_id: int, body: InviteIn, actor: Actor, services: Services) -> InviteOut:
    return await _invite(services, actor, org_id, body)


@router.delete("/orgs/{org_id}/members/{user_id}", status_code=204)
async def revoke_member(org_id: int, user_id: int, actor: Actor, services: Services) -> Response:
    await services.orgs.revoke_membership(actor, org_id, user_id)
    return Response(status_code=204)


@router.get("/orgs/{org_id}/clients", response_model=list[OrgOut])
async def clients(org_id: int, actor: Actor, services: Services) -> list[OrgOut]:
    orgs = await services.orgs.linked_clients(actor, org_id)
    return [OrgOut(id=o.id, name=o.name, kind=o.kind) for o in orgs]


# --- платформа -------------------------------------------------------------


@router.post("/admin/orgs", status_code=201, response_model=OrgOut)
async def admin_create_org(body: OrgIn, actor: Actor, services: Services) -> OrgOut:
    org = await services.orgs.create_org(_platform(actor), body.name, body.kind)
    return OrgOut(id=org.id, name=org.name, kind=org.kind)


@router.post("/admin/orgs/{org_id}/links", status_code=204)
async def admin_link(org_id: int, body: LinkIn, actor: Actor, services: Services) -> Response:
    await services.orgs.link(_platform(actor), org_id, body.client_id)
    return Response(status_code=204)


@router.post("/admin/orgs/{org_id}/invitations", status_code=201, response_model=InviteOut)
async def admin_invite(org_id: int, body: InviteIn, actor: Actor, services: Services) -> InviteOut:
    return await _invite(services, _platform(actor), org_id, body)


# --- мои грузы -------------------------------------------------------------


@router.get("/my/shipments", response_model=list[MyShipment])
async def list_shipments(actor: Actor, services: Services) -> list[MyShipment]:
    views = await my_shipments(services.session_factory, actor, services.clock())
    return [_my(v) for v in views]


@router.post("/my/shipments", status_code=201, response_model=MyShipment)
async def create_shipment(body: ShipmentIn, actor: Actor, services: Services) -> MyShipment:
    row = await services.shipments.create(actor, **body.model_dump())
    logger.info("shipment_created", shipment_id=row.id, by=actor.user_id)
    return _my(await my_shipment(services.session_factory, actor, row.ref, services.clock()))


@router.get("/my/shipments/{ref}", response_model=MyShipment)
async def get_shipment(ref: str, actor: Actor, services: Services) -> MyShipment:
    return _my(await my_shipment(services.session_factory, actor, ref, services.clock()))


@router.patch("/my/shipments/{ref}", response_model=MyShipment)
async def patch_shipment(
    ref: str, body: ShipmentPatch, actor: Actor, services: Services
) -> MyShipment:
    changes = {
        k: v
        for k, v in body.model_dump(exclude_unset=True).items()
        if v is not None or k in PATCH_NULLABLE
    }
    row, route_changed = await services.shipments.update(actor, ref, **changes)
    if route_changed:
        await services.notifier.on_route_changed(row, actor.user_id)
    return _my(await my_shipment(services.session_factory, actor, ref, services.clock()))


@router.post("/my/shipments/{ref}/share", status_code=204)
async def share_shipment(ref: str, body: ShareIn, actor: Actor, services: Services) -> Response:
    await services.shipments.share(actor, ref, body.org_id)
    return Response(status_code=204)


@router.post("/my/shipments/{ref}/archive", status_code=204)
async def archive_shipment(ref: str, actor: Actor, services: Services) -> Response:
    await services.shipments.archive(actor, ref)
    return Response(status_code=204)


@router.get("/my/shipments/{ref}/events", response_model=list[EventOut])
async def list_events(ref: str, actor: Actor, services: Services) -> list[EventOut]:
    return [_event(v) for v in await services.events.list(actor, ref)]


@router.post("/my/shipments/{ref}/events", status_code=201, response_model=EventOut)
async def add_event(ref: str, body: EventIn, actor: Actor, services: Services) -> EventOut:
    row = await services.events.add(actor, ref, **body.model_dump())
    return _event(EventView(row, superseded=False))


@router.put("/my/shipments/{ref}/subscription", status_code=204)
async def put_subscription(
    ref: str, body: SubscriptionIn, actor: Actor, services: Services
) -> Response:
    await services.notifier.set_subscription(
        actor, ref, push=body.push, email=body.email, muted=body.muted
    )
    return Response(status_code=204)
