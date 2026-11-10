"""Схемы запросов и ответов API аккаунтов.

Перечисления (вид события, роль, вид компании, окружение APNs) — Enum/Literal:
неизвестное значение — обычная 422 от FastAPI, до сервисов не доходит.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.db.models import CheckpointEventKind, OrgKind, Role
from app.services.tracking import Shipment

EMAIL_MAX = 254


class CodeIn(BaseModel):
    email: str  # формат не проверяем: на любой адрес — одинаковый 202


class StatusOut(BaseModel):
    status: str


class VerifyIn(BaseModel):
    email: str = Field(max_length=EMAIL_MAX)
    code: str = Field(max_length=16)
    device_name: str = Field(default="", max_length=256)


class MembershipOut(BaseModel):
    org_id: int
    org_name: str
    org_kind: OrgKind
    role: Role
    node_codes: list[str]


class MeOut(BaseModel):
    id: int
    email: str
    name: str | None
    locale: str
    is_platform_admin: bool
    memberships: list[MembershipOut]


class VerifyOut(BaseModel):
    token: str
    me: MeOut


class MePatch(BaseModel):
    name: str | None = Field(default=None, max_length=256)
    locale: Literal["ru", "en"] | None = None


class DeviceIn(BaseModel):
    apns_token: str = Field(max_length=256)
    environment: Literal["sandbox", "production"]


class MemberOut(BaseModel):
    user_id: int
    email: str
    name: str | None
    role: Role
    node_codes: list[str]


class InviteIn(BaseModel):
    email: str = Field(max_length=EMAIL_MAX)
    role: Role
    node_codes: list[str] = Field(default_factory=list, max_length=64)

    @field_validator("email")
    @classmethod
    def _looks_like_email(cls, value: str) -> str:
        if "@" not in value.strip():
            raise ValueError("bad_email")
        return value


class InviteOut(BaseModel):
    invitation_id: int
    mail: Literal["sent", "failed"]


class OrgIn(BaseModel):
    name: str = Field(max_length=256)
    kind: OrgKind


class OrgOut(BaseModel):
    id: int
    name: str
    kind: OrgKind


class LinkIn(BaseModel):
    client_id: int


class ShareIn(BaseModel):
    org_id: int


class MyShipment(BaseModel):
    shipment: Shipment
    org_id: int
    can_manage: bool
    event_nodes: list[str]
    container_no: str | None


class ShipmentIn(BaseModel):
    org_id: int
    container_no: str = Field(max_length=32)
    container_type: str | None = Field(default=None, max_length=32)
    route: list[str] = Field(max_length=64)
    planned_departure_at: datetime
    cargo: str | None = Field(default=None, max_length=2000)
    cargo_en: str | None = Field(default=None, max_length=2000)


class ShipmentPatch(BaseModel):
    container_no: str | None = Field(default=None, max_length=32)
    container_type: str | None = Field(default=None, max_length=32)
    route: list[str] | None = Field(default=None, max_length=64)
    planned_departure_at: datetime | None = None
    cargo: str | None = Field(default=None, max_length=2000)
    cargo_en: str | None = Field(default=None, max_length=2000)


# Поля, которые можно очистить (null); остальные null — «не менять».
PATCH_NULLABLE = frozenset({"container_type", "cargo", "cargo_en"})


class EventIn(BaseModel):
    kind: CheckpointEventKind
    node_code: str = Field(max_length=32)
    occurred_at: datetime | None = None
    hold_code: str | None = Field(default=None, max_length=32)
    note: str | None = None  # длину проверяет сервис (note_too_long)
    vessel: str | None = None
    supersedes_id: int | None = None


class EventOut(BaseModel):
    id: int
    kind: CheckpointEventKind
    node_code: str
    occurred_at: datetime
    hold_code: str | None
    note: str | None
    vessel: str | None
    source: str
    created_by: int | None
    supersedes_id: int | None
    created_at: datetime
    superseded: bool


class SubscriptionIn(BaseModel):
    push: bool
    email: bool
    muted: bool
