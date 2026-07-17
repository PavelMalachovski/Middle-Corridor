"""SQLAlchemy-модели предметной области (§6 спеки).

Все enum'ы храним как VARCHAR + CHECK (native_enum=False): это упрощает
миграции при добавлении значений и позволяет гонять юнит-тесты на SQLite.
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
