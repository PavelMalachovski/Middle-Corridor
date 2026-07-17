"""Погодный предиктор остановки портов — ядро продукта (§7.1).

Каждый прогон: по всем портам с is_weather_tracked=true запрашивается
текущий ветер И почасовой прогноз. Уровень риска — максимум из текущих
условий и пика прогноза в горизонте (продукт предупреждает «порт встанет
завтра», а не констатирует шторм постфактум). Снимок в БД — текущий ветер.

Антиспам через жизненный цикл: активный алерт «живёт», пока держится
условие. Публикации в канал:
- эскалация до warning/critical (уровень вырос) → алерт;
- уход ниже warning → «отбой»;
- watch и понижение critical→warning — тихие переходы (только БД).

ВАЖНО: пороги — стартовые значения из конфига (§9). Их нужно калибровать
по фактическим остановкам портов после накопления реальных данных — это
и есть уникальная ценность продукта.
"""

from dataclasses import dataclass, field

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.models import AlertLevel, Port
from app.db.repositories.weather import WeatherRepository
from app.integrations.weather.base import WeatherProvider, WindObservation, WindReport
from app.services.formatting import format_weather_alert, format_weather_all_clear
from app.services.sinks import MessageSink

logger = structlog.get_logger(__name__)

_RANK = {AlertLevel.watch: 1, AlertLevel.warning: 2, AlertLevel.critical: 3}


@dataclass(frozen=True, slots=True)
class WindThresholds:
    """Пороги ветра (м/с). Стартовые значения — требуют калибровки."""

    watch_wind: float
    warning_wind: float
    warning_gust: float
    critical_wind: float
    critical_gust: float

    @classmethod
    def from_settings(cls, settings: Settings) -> "WindThresholds":
        return cls(
            watch_wind=settings.weather_watch_wind,
            warning_wind=settings.weather_warning_wind,
            warning_gust=settings.weather_warning_gust,
            critical_wind=settings.weather_critical_wind,
            critical_gust=settings.weather_critical_gust,
        )


def evaluate_level(
    wind_speed: float, wind_gust: float, thresholds: WindThresholds
) -> AlertLevel | None:
    """Уровень риска по устойчивому ветру и порывам; None — условия рабочие."""
    if wind_speed >= thresholds.critical_wind or wind_gust >= thresholds.critical_gust:
        return AlertLevel.critical
    if wind_speed >= thresholds.warning_wind or wind_gust >= thresholds.warning_gust:
        return AlertLevel.warning
    if wind_speed >= thresholds.watch_wind:
        return AlertLevel.watch
    return None


def _rank(level: AlertLevel | None) -> int:
    return _RANK[level] if level is not None else 0


def forecast_peak(
    forecast: list[WindObservation], thresholds: WindThresholds
) -> tuple[AlertLevel, WindObservation] | None:
    """Самый высокий уровень в прогнозе и первый час, когда он достигается."""
    peak: tuple[AlertLevel, WindObservation] | None = None
    for hour in forecast:
        level = evaluate_level(hour.wind_speed, hour.wind_gust, thresholds)
        if level is None:
            continue
        if peak is None or _rank(level) > _rank(peak[0]):
            peak = (level, hour)
    return peak


@dataclass(slots=True)
class WeatherPollStats:
    """Итог одного прогона — для ответа админу и логов."""

    ports_polled: int = 0
    errors: int = 0
    transitions: list[str] = field(default_factory=list)  # "AKTAU: — → warning"


class WeatherPredictor:
    """Опрос погоды по портам и жизненный цикл алертов."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        provider: WeatherProvider,
        thresholds: WindThresholds,
        sink: MessageSink | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._provider = provider
        self._thresholds = thresholds
        self._sink = sink

    async def poll_once(self) -> WeatherPollStats:
        """Один прогон предиктора по всем отслеживаемым портам.

        Ошибка по одному порту не прерывает обработку остальных.
        """
        stats = WeatherPollStats()
        async with self._session_factory() as session:
            repo = WeatherRepository(session)
            ports = await repo.get_tracked_ports()
            for port in ports:
                try:
                    report = await self._provider.get_wind(port.lat, port.lon)
                except Exception as exc:  # noqa: BLE001 — джоба не должна падать
                    logger.error("weather_fetch_failed", port=port.code, error=str(exc))
                    stats.errors += 1
                    continue
                await repo.add_snapshot(port.id, report.current)
                stats.ports_polled += 1
                transition = await self._apply_transition(repo, port, report)
                if transition is not None:
                    stats.transitions.append(transition)
            await session.commit()
        return stats

    async def _apply_transition(
        self, repo: WeatherRepository, port: Port, report: WindReport
    ) -> str | None:
        """Применяет переход уровня; возвращает его описание (или None без изменений)."""
        obs = report.current
        current_level = evaluate_level(obs.wind_speed, obs.wind_gust, self._thresholds)
        peak = forecast_peak(report.forecast, self._thresholds)

        # Эффективный уровень: максимум текущих условий и пика прогноза.
        # Алерт «звучит» заранее и держится, пока не стихнет и прогноз.
        level = current_level
        peak_obs: WindObservation | None = None
        if peak is not None and _rank(peak[0]) > _rank(current_level):
            level, peak_obs = peak

        active = await repo.get_active_alert(port.id)
        active_level = active.level if active is not None else None

        if _rank(level) == _rank(active_level):
            return None  # уровень не изменился — антиспам, ничего не делаем

        if active is not None:
            await repo.close_alert(active, ts=obs.ts)
        if level is not None:
            if peak_obs is not None:
                summary = (
                    f"Прогноз: ветер до {peak_obs.wind_speed:.0f} м/с, "
                    f"порывы до {peak_obs.wind_gust:.0f} м/с к {peak_obs.ts:%H:%M} UTC"
                )
            else:
                summary = f"Ветер {obs.wind_speed:.0f} м/с, порывы до {obs.wind_gust:.0f} м/с"
            await repo.open_alert(port.id, level, summary, ts=obs.ts)

        logger.info(
            "weather_alert_transition",
            port=port.code,
            from_level=active_level.value if active_level else None,
            to_level=level.value if level else None,
            wind=obs.wind_speed,
            gust=obs.wind_gust,
            forecast_driven=peak_obs is not None,
        )

        warning_rank = _RANK[AlertLevel.warning]
        if _rank(level) > _rank(active_level) and _rank(level) >= warning_rank:
            # уровень вырос до warning/critical — алерт в канал
            await self._publish(
                format_weather_alert(port, level, obs, forecast_peak=peak_obs)  # type: ignore[arg-type]
            )
        elif _rank(active_level) >= warning_rank and _rank(level) < warning_rank:
            # условие ушло ниже warning (и по прогнозу тоже) — отбой
            await self._publish(format_weather_all_clear(port, obs))

        old = active_level.value if active_level else "—"
        new = level.value if level else "—"
        suffix = " (по прогнозу)" if peak_obs is not None else ""
        return f"{port.code}: {old} → {new}{suffix}"

    async def _publish(self, text: str) -> None:
        if self._sink is None:
            return
        try:
            await self._sink.publish(text)
        except Exception as exc:  # noqa: BLE001 — сбой публикации не роняет прогон
            logger.error("weather_alert_publish_failed", error=str(exc))
