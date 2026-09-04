"""Мок-узлы (с погодой из синтетического поля ветра), новости и ручные сводки."""

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from app.integrations.mock.wind import wind_at
from app.services.corridor import NODES, NodeKind
from app.services.map_snapshot import NewsSummary, NodeStatus
from app.services.status_aggregator import ReportStatus
from app.services.weather_predictor import WindThresholds, evaluate_level


def _floor_minutes(ts: datetime, minutes: int) -> datetime:
    return ts.replace(minute=ts.minute - ts.minute % minutes, second=0, microsecond=0)


class MockNodeSource:
    """Узлы справочника; портам — ветер из поля и уровень по боевым порогам."""

    def __init__(self, clock: Callable[[], datetime], thresholds: WindThresholds) -> None:
        self._clock = clock
        self._thresholds = thresholds

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
                payload={"border": "Бёюк-Кясик / Гардабани", "delay_hours": 14},
                note="Досмотр на азербайджанской стороне, очередь около 40 вагонов",
                ts=now - timedelta(hours=7),
            ),
            ReportStatus(
                report_type="rate",
                port_name="Баку (Алят)",
                payload={"rate_usd": 3450},
                note="40' HC Сиань — Констанца, all-in, сентябрь",
                ts=now - timedelta(hours=26),
            ),
        ]
