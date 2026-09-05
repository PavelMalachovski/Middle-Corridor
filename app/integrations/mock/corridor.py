"""Мок-узлы (с погодой из синтетического поля ветра), новости и ручные сводки."""

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from app.integrations.mock.wind import wind_at
from app.services.corridor import NODES, NodeKind
from app.services.map_snapshot import NewsSummary, NodeStatus, WindHour
from app.services.status_aggregator import ReportStatus
from app.services.weather_predictor import WindThresholds, evaluate_level


def _floor_minutes(ts: datetime, minutes: int) -> datetime:
    return ts.replace(minute=ts.minute - ts.minute % minutes, second=0, microsecond=0)


def _floor_hour(ts: datetime) -> datetime:
    return ts.replace(minute=0, second=0, microsecond=0)


FORECAST_PAST_H = 6
FORECAST_FUTURE_H = 48


class MockNodeSource:
    """Узлы справочника; портам — ветер из поля и уровень по боевым порогам."""

    def __init__(self, clock: Callable[[], datetime], thresholds: WindThresholds) -> None:
        self._clock = clock
        self._thresholds = thresholds
        self._hour_cache: dict[tuple[str, datetime], WindHour] = {}

    def _hour(self, code: str, lat: float, lon: float, ts: datetime) -> WindHour:
        """Ветер и уровень в узле на начало часа; поле детерминировано — кэшируем."""
        key = (code, ts)
        cached = self._hour_cache.get(key)
        if cached is not None:
            return cached
        if len(self._hour_cache) > 20_000:
            self._hour_cache.clear()
        speed, gust, _direction = wind_at(lat, lon, ts)
        hour = WindHour(
            ts=ts, speed=speed, gust=gust, level=evaluate_level(speed, gust, self._thresholds)
        )
        self._hour_cache[key] = hour
        return hour

    def _forecast(self, code: str, lat: float, lon: float, now: datetime) -> list[WindHour]:
        start = _floor_hour(now) - timedelta(hours=FORECAST_PAST_H)
        return [
            self._hour(code, lat, lon, start + timedelta(hours=i))
            for i in range(FORECAST_PAST_H + FORECAST_FUTURE_H + 1)
        ]

    async def downtime_hours(self, at: datetime, window_hours: int) -> tuple[float, int]:
        """Часы critical по всем портам за окно и число портов с остановками."""
        end = _floor_hour(at)
        total = 0
        stopped = 0
        for node in NODES.values():
            if node.kind != NodeKind.port:
                continue
            hours = sum(
                1
                for i in range(window_hours)
                if self._hour(node.code, node.lat, node.lon, end - timedelta(hours=i)).level
                == "critical"
            )
            total += hours
            if hours:
                stopped += 1
        return float(total), stopped

    async def list_nodes(self, at: datetime | None = None) -> list[NodeStatus]:
        now = at or self._clock()
        weather_ts = _floor_minutes(now, 15)
        result: list[NodeStatus] = []
        for node in NODES.values():
            status = NodeStatus(
                code=node.code,
                name=node.name,
                country=node.country,
                leg=node.leg,
                kind=node.kind,
                lat=node.lat,
                lon=node.lon,
                name_en=node.name_en,
                country_en=node.country_en,
            )
            if node.kind == NodeKind.port:
                speed, gust, direction = wind_at(node.lat, node.lon, weather_ts)
                level = evaluate_level(speed, gust, self._thresholds)
                status = status.model_copy(
                    update={
                        "is_weather_tracked": True,
                        "wind_speed": speed,
                        "wind_gust": gust,
                        "wind_dir": direction,
                        "weather_ts": weather_ts,
                        "alert_level": level,
                        "alert_message": (
                            f"Ветер {speed:.0f} м/с, порывы до {gust:.0f} м/с" if level else None
                        ),
                        "forecast": self._forecast(node.code, node.lat, node.lon, now),
                    }
                )
            result.append(status)
        return result


_NEWS: list[dict[str, Any]] = [
    {
        "source": "Middle Corridor Wire",
        "title": "Объём перевозок по Среднему коридору за 8 месяцев вырос на 62%",
        "summary": "Основной прирост — транзит Китай → Европа через Актау и Алят; "
        "доля контейнерных поездов впервые превысила половину объёма.",
        "hours_ago": 1.5,
    },
    {
        "source": "Caspian Ports Bulletin",
        "title": "Актау: штормовое предупреждение, паромные операции приостановлены",
        "summary": "Ветер до 20 м/с с порывами выше 21 м/с. Швартовка паромов в Актау "
        "и Курыке закрыта, ожидается улучшение к концу суток.",
        "hours_ago": 3,
    },
    {
        "source": "Caspian Ports Bulletin",
        "title": "ASCO выводит на линию Курык — Алят дополнительный паром",
        "summary": "Седьмое судно на линии должно сократить очередь составов в Курыке "
        "и вернуть интервал отправлений к 8–10 часам.",
        "hours_ago": 9,
    },
    {
        "source": "Rail Eurasia",
        "title": "На границе Бёюк-Кясик — Гардабани запущено электронное "
        "предварительное декларирование",
        "summary": "Пилот на грузовых составах ТМТМ: среднее время оформления должно "
        "снизиться с 18 до 8 часов.",
        "hours_ago": 14,
    },
    {
        "source": "Black Sea Logistics",
        "title": "Констанца: новая ро-ро линия из Поти — два отправления в неделю",
        "summary": "Расписание синхронизировано с контейнерными поездами из Тбилиси; "
        "первый рейс уже принят в порту.",
        "hours_ago": 22,
    },
    {
        "source": "Rail Eurasia",
        "title": "КТЖ увеличила пропускную способность участка Бейнеу — Мангистау на 30%",
        "summary": "Завершена реконструкция разъездов; участок — узкое место маршрута "
        "к каспийским портам.",
        "hours_ago": 31,
    },
    {
        "source": "Steppe Business",
        "title": "Ставки на 40' контейнер Китай — Европа по ТМТМ стабилизировались около $3 500",
        "summary": "После летнего роста ставки вышли на плато; экспедиторы ждут осеннего "
        "сезона высокого спроса.",
        "hours_ago": 40,
    },
    {
        "source": "Middle Corridor Wire",
        "title": "Хоргос: очередь на перегруз сократилась до 18 часов",
        "summary": "Дополнительная смена на терминале Алтынколь; неделей ранее ожидание "
        "доходило до двух суток.",
        "hours_ago": 55,
    },
]


class MockNewsSource:
    def __init__(self, clock: Callable[[], datetime]) -> None:
        self._clock = clock

    async def list_news(self, limit: int, at: datetime | None = None) -> list[NewsSummary]:
        now = at or self._clock()
        return [
            NewsSummary(
                id=idx + 1,
                source=item["source"],
                title=item["title"],
                summary=item["summary"],
                url=f"https://example.org/mock/news/{idx + 1}",
                published_at=now - timedelta(hours=item["hours_ago"]),
            )
            for idx, item in enumerate(_NEWS[:limit])
        ]


class MockReportSource:
    def __init__(self, clock: Callable[[], datetime]) -> None:
        self._clock = clock

    async def list_reports(self, at: datetime | None = None) -> list[ReportStatus]:
        now = at or self._clock()
        return [
            ReportStatus(
                report_type="queue",
                port_name="Актау",
                port_code="AKTAU",
                payload={
                    "vessels_waiting": 5,
                    "ferry_expected": (now + timedelta(hours=20)).date().isoformat(),
                },
                note="Швартовка закрыта по ветру, пять составов ждут погрузки",
                ts=now - timedelta(hours=3),
            ),
            ReportStatus(
                report_type="border_delay",
                port_name=None,
                payload={
                    "border": "Бёюк-Кясик / Гардабани",
                    "border_code": "BOYUK_KASIK",
                    "delay_hours": 14,
                },
                note="Досмотр на азербайджанской стороне, очередь около 40 вагонов",
                ts=now - timedelta(hours=7),
            ),
            ReportStatus(
                report_type="rate",
                port_name="Баку (Алят)",
                port_code="BAKU_ALAT",
                payload={"rate_usd": 3450},
                note="40' HC Сиань — Констанца, all-in, сентябрь",
                ts=now - timedelta(hours=26),
            ),
        ]
