"""SQLAlchemy-модели предметной области (§6 спеки).

Все enum'ы храним как VARCHAR (native_enum=False, без CHECK-ограничения):
это упрощает миграции при добавлении значений и позволяет гонять юнит-тесты
на SQLite. Допустимые значения контролирует только приложение (Python-enum).
"""

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base

# JSONB в Postgres, обычный JSON в SQLite (для юнит-тестов)
JsonVariant = JSON().with_variant(JSONB(), "postgresql")


def _str_enum(enum_cls: type[enum.Enum]) -> Enum:
    return Enum(
        enum_cls,
        native_enum=False,
        length=32,
        values_callable=lambda e: [member.value for member in e],
    )


class CorridorLeg(enum.StrEnum):
    """Плечо коридора."""

    caspian = "caspian"
    black_sea = "black_sea"
    rail_cis = "rail_cis"
    rail_caucasus = "rail_caucasus"
    europe = "europe"


class PositionSource(enum.StrEnum):
    aisstream = "aisstream"
    vesselapi = "vesselapi"


class PortEventType(enum.StrEnum):
    arrival = "arrival"
    departure = "departure"


class AlertLevel(enum.StrEnum):
    watch = "watch"
    warning = "warning"
    critical = "critical"


class ClosureCause(enum.StrEnum):
    """Причина остановки порта. В калибровку предиктора идёт только ветер."""

    wind = "wind"  # ветер/шторм — то, что предсказывает предиктор
    other = "other"  # туман, лёд, техника, решения властей


class ReportType(enum.StrEnum):
    queue = "queue"
    rate = "rate"
    border_delay = "border_delay"
    note = "note"


class Port(Base):
    """Порт или узел коридора."""

    __tablename__ = "ports"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    country: Mapped[str] = mapped_column(String(64))
    leg: Mapped[CorridorLeg] = mapped_column(_str_enum(CorridorLeg))
    lat: Mapped[float]
    lon: Mapped[float]
    is_weather_tracked: Mapped[bool] = mapped_column(default=False)


class Vessel(Base):
    """Судно под наблюдением (в основном паромы Каспия)."""

    __tablename__ = "vessels"

    id: Mapped[int] = mapped_column(primary_key=True)
    mmsi: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    imo: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    name: Mapped[str] = mapped_column(String(128))
    operator: Mapped[str | None] = mapped_column(String(128), nullable=True)
    leg: Mapped[CorridorLeg] = mapped_column(_str_enum(CorridorLeg), default=CorridorLeg.caspian)
    is_tracked: Mapped[bool] = mapped_column(default=True)


class VesselPosition(Base):
    """Позиция судна из AIS."""

    __tablename__ = "vessel_positions"
    __table_args__ = (Index("ix_vessel_positions_vessel_ts", "vessel_id", "ts"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    vessel_id: Mapped[int] = mapped_column(ForeignKey("vessels.id", ondelete="CASCADE"))
    lat: Mapped[float]
    lon: Mapped[float]
    sog: Mapped[float | None] = mapped_column(nullable=True)  # скорость, узлы
    cog: Mapped[float | None] = mapped_column(nullable=True)  # курс, градусы
    nav_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source: Mapped[PositionSource] = mapped_column(_str_enum(PositionSource))

    vessel: Mapped[Vessel] = relationship()


class PortEvent(Base):
    """Заход/отход судна в порту."""

    __tablename__ = "port_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    port_id: Mapped[int] = mapped_column(ForeignKey("ports.id", ondelete="CASCADE"))
    vessel_id: Mapped[int] = mapped_column(ForeignKey("vessels.id", ondelete="CASCADE"))
    event_type: Mapped[PortEventType] = mapped_column(_str_enum(PortEventType))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source: Mapped[PositionSource] = mapped_column(_str_enum(PositionSource))

    port: Mapped[Port] = relationship()
    vessel: Mapped[Vessel] = relationship()


class WeatherSnapshot(Base):
    """Снимок погоды по порту."""

    __tablename__ = "weather_snapshots"
    __table_args__ = (Index("ix_weather_snapshots_port_ts", "port_id", "ts"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    port_id: Mapped[int] = mapped_column(ForeignKey("ports.id", ondelete="CASCADE"))
    wind_speed: Mapped[float]  # м/с, устойчивый ветер
    wind_gust: Mapped[float]  # м/с, порывы
    wind_dir: Mapped[float]  # градусы
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    raw: Mapped[dict[str, Any] | None] = mapped_column(JsonVariant, nullable=True)

    port: Mapped[Port] = relationship()


class WindGrid(Base):
    """Снимок прогноза ветра по сетке над морями — поле ветра карты и её replay.

    hours — ISO-часы прогноза (UTC), points — [{lat, lon, s: [...], g: [...], d: [...]}]
    с рядами по этим часам (null, где провайдер не ответил).
    """

    __tablename__ = "wind_grids"

    id: Mapped[int] = mapped_column(primary_key=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    step_deg: Mapped[float]
    hours: Mapped[list[str]] = mapped_column(JsonVariant)
    points: Mapped[list[dict[str, Any]]] = mapped_column(JsonVariant)
    source: Mapped[str] = mapped_column(String(32), default="open-meteo")


class WeatherAlert(Base):
    """Погодный алерт.

    «Живёт», пока держится условие: повторные публикации того же уровня не
    создаются (антиспам), при снятии условия закрывается (closed_at).
    """

    __tablename__ = "weather_alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    port_id: Mapped[int] = mapped_column(ForeignKey("ports.id", ondelete="CASCADE"))
    level: Mapped[AlertLevel] = mapped_column(_str_enum(AlertLevel))
    message: Mapped[str] = mapped_column(Text)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, index=True)

    port: Mapped[Port] = relationship()


class PortClosure(Base):
    """Факт остановки порта (швартовка/погрузка прекращены).

    Журнал фактов — эталон для калибровки порогов ветра: предиктор сверяется
    с ним, а не с «ощущениями». ended_at = NULL — порт всё ещё закрыт.
    """

    __tablename__ = "port_closures"
    __table_args__ = (Index("ix_port_closures_port_started", "port_id", "started_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    port_id: Mapped[int] = mapped_column(ForeignKey("ports.id", ondelete="CASCADE"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cause: Mapped[ClosureCause] = mapped_column(_str_enum(ClosureCause))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reported_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # Telegram id
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    port: Mapped[Port] = relationship()


class NewsItem(Base):
    """Новость коридора."""

    __tablename__ = "news_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(128))
    url: Mapped[str] = mapped_column(String(1024), unique=True)
    external_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    title: Mapped[str] = mapped_column(String(512))
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Перевод/суммаризация на русский (LLM); NULL = оригинал уже русский
    # или перевод ещё не выполнялся
    title_ru: Mapped[str | None] = mapped_column(String(512), nullable=True)
    summary_ru: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_sent: Mapped[bool] = mapped_column(default=False, index=True)


class TrustedSource(Base):
    """Доверенный источник ручных данных (whitelist)."""

    __tablename__ = "trusted_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    tg_user_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    name: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(64))  # port_agent | operator | forwarder | ...
    is_active: Mapped[bool] = mapped_column(default=True)


class ManualReport(Base):
    """Оперативные данные от доверенного источника."""

    __tablename__ = "manual_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("trusted_sources.id", ondelete="CASCADE"))
    port_id: Mapped[int | None] = mapped_column(
        ForeignKey("ports.id", ondelete="SET NULL"), nullable=True
    )
    report_type: Mapped[ReportType] = mapped_column(_str_enum(ReportType))
    payload: Mapped[dict[str, Any]] = mapped_column(JsonVariant, default=dict)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    is_published: Mapped[bool] = mapped_column(default=False)

    source: Mapped[TrustedSource] = relationship()
    port: Mapped[Port | None] = relationship()


class Subscriber(Base):
    """Пользователь бота (для будущих рассылок)."""

    __tablename__ = "subscribers"

    id: Mapped[int] = mapped_column(primary_key=True)
    tg_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --- Аккаунты, доступ, отправки и события на чекпоинтах ---


class OrgKind(enum.StrEnum):
    forwarder = "forwarder"
    client = "client"
    platform = "platform"


class Role(enum.StrEnum):
    owner = "owner"
    admin = "admin"
    agent = "agent"
    viewer = "viewer"


class CheckpointEventKind(enum.StrEnum):
    arrived = "arrived"
    departed = "departed"
    held = "held"
    released = "released"


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    kind: Mapped[OrgKind] = mapped_column(_str_enum(OrgKind))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    locale: Mapped[str] = mapped_column(String(8), default="ru")
    is_platform_admin: Mapped[bool] = mapped_column(default=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "org_id", name="uq_memberships_user_org"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    role: Mapped[Role] = mapped_column(_str_enum(Role))
    # Коды узлов, где агент вправе отмечать события; пусто = ограничения нет
    node_codes: Mapped[list[str]] = mapped_column(JsonVariant, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Invitation(Base):
    __tablename__ = "invitations"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    email: Mapped[str] = mapped_column(String(320), index=True)
    role: Mapped[Role] = mapped_column(_str_enum(Role))
    node_codes: Mapped[list[str]] = mapped_column(JsonVariant, default=list)
    invited_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LoginCode(Base):
    __tablename__ = "login_codes"
    __table_args__ = (
        Index("ix_login_codes_email_created", "email", "created_at"),
        Index("ix_login_codes_ip_created", "ip", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320))
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    code_hash: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(default=0)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuthSession(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    device_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OrgLink(Base):
    """Экспедитор → клиент: клиент видит отправки, которыми с ним поделились."""

    __tablename__ = "org_links"

    forwarder_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    client_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ShipmentRow(Base):
    """Отправка в БД (не путать с pydantic tracking.Shipment)."""

    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(primary_key=True)
    ref: Mapped[str] = mapped_column(String(64), unique=True)
    org_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    container_no: Mapped[str | None] = mapped_column(String(32), nullable=True)
    container_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    route: Mapped[list[str]] = mapped_column(JsonVariant, default=list)  # коды узлов по порядку
    planned_departure_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cargo: Mapped[str | None] = mapped_column(Text, nullable=True)
    cargo_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    cargo_manifest: Mapped[dict[str, Any] | None] = mapped_column(JsonVariant, nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ShipmentShare(Base):
    """Отправка расшарена организации-клиенту."""

    __tablename__ = "shipment_shares"

    shipment_id: Mapped[int] = mapped_column(
        ForeignKey("shipments.id", ondelete="CASCADE"), primary_key=True
    )
    org_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ShipmentEventRow(Base):
    """Событие на чекпоинте; правка = новая запись с supersedes_id."""

    __tablename__ = "shipment_events"
    __table_args__ = (Index("ix_shipment_events_shipment_at", "shipment_id", "occurred_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id", ondelete="CASCADE"))
    kind: Mapped[CheckpointEventKind] = mapped_column(_str_enum(CheckpointEventKind))
    node_code: Mapped[str] = mapped_column(String(32))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    hold_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    vessel: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="manual")
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    supersedes_id: Mapped[int | None] = mapped_column(
        ForeignKey("shipment_events.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ShipmentRevision(Base):
    """История правок полей отправки."""

    __tablename__ = "shipment_revisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_id: Mapped[int] = mapped_column(
        ForeignKey("shipments.id", ondelete="CASCADE"), index=True
    )
    changed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    before: Mapped[dict[str, Any]] = mapped_column(JsonVariant, default=dict)
    after: Mapped[dict[str, Any]] = mapped_column(JsonVariant, default=dict)


class Subscription(Base):
    """Персональные переопределения уведомлений (mute / канал выключен)."""

    __tablename__ = "subscriptions"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    shipment_id: Mapped[int] = mapped_column(
        ForeignKey("shipments.id", ondelete="CASCADE"), primary_key=True
    )
    push: Mapped[bool] = mapped_column(default=True)
    email: Mapped[bool] = mapped_column(default=True)
    muted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    apns_token: Mapped[str] = mapped_column(String(256), unique=True)
    environment: Mapped[str] = mapped_column(String(16), default="sandbox")
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(64))
    entity: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JsonVariant, default=dict)
