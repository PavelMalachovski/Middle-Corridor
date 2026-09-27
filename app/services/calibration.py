"""Проверка предиктора по фактам: точность алертов и подбор порогов ветра.

Чистые функции без БД — их гоняют юнит-тесты и PredictorAccuracyService.

Два уровня сверки с журналом фактических остановок (port_closures):

1. **События.** Остановка «предсказана», если алерт warning+ был открыт в
   окне [начало − before, начало + after]. Эпизод алертов (цепочка
   warning→critical без разрыва) — «ложная тревога», если за время эпизода
   и grace после него порт так и не встал. Метрики, принятые в верификации
   прогнозов погоды:
   - POD — доля предсказанных остановок;
   - FAR — доля ложных тревог;
   - CSI = hits / (hits + misses + false alarms): не раздувается тысячами
     спокойных часов, в отличие от accuracy.

2. **Часы.** Каждое наблюдение ветра помечено «порт стоял / работал».
   Правило «ветер ≥ W или порывы ≥ G → стоит» оценивается перебором сетки
   (W, G). Лучшее по CSI — кандидат в пороги critical. Самое точное среди
   ловящих ≥ 90 % остановок — кандидат в warning.

Пороги сами не меняются (CLAUDE.md: только по фактам и только руками).
Подбор — подсказка админу, а не автопилот.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median

# Окна сверки событий (см. docstring модуля)
HIT_BEFORE = timedelta(hours=6)
HIT_AFTER = timedelta(hours=1)  # опрос раз в 45 мин: алерт может открыться чуть позже факта
FALSE_ALARM_GRACE = timedelta(hours=12)
EPISODE_GAP = timedelta(hours=1)  # warning закрылся и сразу открылся critical — один эпизод

# Меньше данных — подбор порогов не делаем: переобучимся на паре штормов
MIN_CLOSURES = 2
MIN_CLOSED_SAMPLES = 6
WARNING_MIN_POD = 0.9

WIND_GRID = tuple(x / 2 for x in range(16, 51))  # 8.0 … 25.0 м/с, шаг 0.5
GUST_GRID = tuple(float(x) for x in range(10, 33))  # 10 … 32 м/с, шаг 1


@dataclass(frozen=True, slots=True)
class Interval:
    """Отрезок времени; end=None — ещё длится (до now)."""

    start: datetime
    end: datetime | None = None

    def end_or(self, now: datetime) -> datetime:
        return self.end if self.end is not None else now


def _overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start <= b_end and b_start <= a_end


def merge_episodes(
    alerts: Iterable[Interval], now: datetime, gap: timedelta = EPISODE_GAP
) -> list[Interval]:
    """Склеивает алерты в эпизоды: эскалация warning→critical — один эпизод."""
    episodes: list[Interval] = []
    for alert in sorted(alerts, key=lambda a: a.start):
        if episodes:
            last = episodes[-1]
            if alert.start <= last.end_or(now) + gap:
                if last.end is None or alert.end is None:
                    end = None
                else:
                    end = max(last.end, alert.end)
                episodes[-1] = Interval(last.start, end)
                continue
        episodes.append(alert)
    return episodes


def _ratio(num: int, den: int) -> float | None:
    return num / den if den else None


@dataclass(frozen=True, slots=True)
class EventScore:
    """Сверка алертов с фактами за период."""

    closures: int
    hits: int
    episodes: int
    false_alarms: int
    lead_hours: tuple[float, ...] = ()

    @property
    def misses(self) -> int:
        return self.closures - self.hits

    @property
    def pod(self) -> float | None:
        return _ratio(self.hits, self.closures)

    @property
    def far(self) -> float | None:
        return _ratio(self.false_alarms, self.episodes)

    @property
    def csi(self) -> float | None:
        return _ratio(self.hits, self.hits + self.misses + self.false_alarms)

    @property
    def median_lead_h(self) -> float | None:
        return median(self.lead_hours) if self.lead_hours else None


def score_events(
    closures: Sequence[Interval],
    alerts: Iterable[Interval],
    now: datetime,
    *,
    before: timedelta = HIT_BEFORE,
    after: timedelta = HIT_AFTER,
    grace: timedelta = FALSE_ALARM_GRACE,
) -> EventScore:
    """Остановки против алертов warning+ (alerts — сырые строки, эпизоды склеим сами)."""
    episodes = merge_episodes(alerts, now)
    hits = 0
    leads: list[float] = []
    for closure in closures:
        lo, hi = closure.start - before, closure.start + after
        matched = [e for e in episodes if _overlaps(e.start, e.end_or(now), lo, hi)]
        if not matched:
            continue
        hits += 1
        first = min(e.start for e in matched)
        leads.append(max(0.0, (closure.start - first).total_seconds() / 3600))
    false_alarms = 0
    for episode in episodes:
        lo, hi = episode.start, episode.end_or(now) + grace
        if not any(_overlaps(c.start, c.end_or(now), lo, hi) for c in closures):
            false_alarms += 1
    return EventScore(
        closures=len(closures),
        hits=hits,
        episodes=len(episodes),
        false_alarms=false_alarms,
        lead_hours=tuple(leads),
    )


@dataclass(frozen=True, slots=True)
class Sample:
    """Наблюдение ветра с меткой «порт стоял»."""

    ts: datetime
    wind: float
    gust: float
    closed: bool


def label_samples(
    observations: Iterable[tuple[datetime, float, float]],
    closures: Sequence[Interval],
    now: datetime,
) -> list[Sample]:
    """(ts, ветер, порывы) → метка по журналу остановок."""
    return [
        Sample(
            ts=ts,
            wind=wind,
            gust=gust,
            closed=any(c.start <= ts <= c.end_or(now) for c in closures),
        )
        for ts, wind, gust in observations
    ]


@dataclass(frozen=True, slots=True)
class RuleScore:
    """Правило «ветер ≥ wind или порывы ≥ gust → порт стоит» на размеченных часах."""

    wind: float
    gust: float
    hits: int
    misses: int
    false_alarms: int
    correct_negatives: int

    @property
    def pod(self) -> float | None:
        return _ratio(self.hits, self.hits + self.misses)

    @property
    def far(self) -> float | None:
        return _ratio(self.false_alarms, self.hits + self.false_alarms)

    @property
    def csi(self) -> float | None:
        return _ratio(self.hits, self.hits + self.misses + self.false_alarms)


def score_rule(samples: Sequence[Sample], wind: float, gust: float) -> RuleScore:
    hits = misses = false_alarms = correct_negatives = 0
    for s in samples:
        predicted = s.wind >= wind or s.gust >= gust
        if s.closed:
            if predicted:
                hits += 1
            else:
                misses += 1
        elif predicted:
            false_alarms += 1
        else:
            correct_negatives += 1
    return RuleScore(wind, gust, hits, misses, false_alarms, correct_negatives)


@dataclass(frozen=True, slots=True)
class Calibration:
    """Итог подбора порогов для одного порта."""

    samples: int
    closed_samples: int
    closures: int
    current_warning: RuleScore
    current_critical: RuleScore
    best_critical: RuleScore | None  # max CSI
    best_warning: RuleScore | None  # POD ≥ 0.9 при минимальном FAR

    @property
    def enough_data(self) -> bool:
        return self.best_critical is not None


def _search(
    samples: Sequence[Sample], wind_grid: Sequence[float], gust_grid: Sequence[float]
) -> list[RuleScore]:
    """Все правила сетки. Спокойные часы ниже минимума сетки ни одно правило
    не сработает — их считаем один раз, а не на каждой ячейке (год часов × сетка)."""
    min_w, min_g = min(wind_grid), min(gust_grid)
    closed = [s for s in samples if s.closed]
    open_ = [s for s in samples if not s.closed]
    candidates = [s for s in open_ if s.wind >= min_w or s.gust >= min_g]
    out: list[RuleScore] = []
    for w in wind_grid:
        for g in gust_grid:
            hits = sum(1 for s in closed if s.wind >= w or s.gust >= g)
            fa = sum(1 for s in candidates if s.wind >= w or s.gust >= g)
            out.append(RuleScore(w, g, hits, len(closed) - hits, fa, len(open_) - fa))
    return out


def calibrate(
    samples: Sequence[Sample],
    closures: int,
    *,
    warning: tuple[float, float],
    critical: tuple[float, float],
    wind_grid: Sequence[float] = WIND_GRID,
    gust_grid: Sequence[float] = GUST_GRID,
) -> Calibration:
    """Подбор порогов; при малом числе фактов best_* = None (подсказки не будет)."""
    closed_samples = sum(1 for s in samples if s.closed)
    current_warning = score_rule(samples, *warning)
    current_critical = score_rule(samples, *critical)
    best_critical = best_warning = None
    if closures >= MIN_CLOSURES and closed_samples >= MIN_CLOSED_SAMPLES:
        rules = _search(samples, wind_grid, gust_grid)
        # при равном CSI — меньше ложных тревог, затем пороги повыше (осторожнее)
        best_critical = max(rules, key=lambda r: (r.csi or 0.0, -(r.far or 0.0), r.wind, r.gust))
        sensitive = [r for r in rules if (r.pod or 0.0) >= WARNING_MIN_POD]
        if sensitive:
            best_warning = min(
                sensitive, key=lambda r: (r.far or 0.0, -(r.csi or 0.0), -r.wind, -r.gust)
            )
    return Calibration(
        samples=len(samples),
        closed_samples=closed_samples,
        closures=closures,
        current_warning=current_warning,
        current_critical=current_critical,
        best_critical=best_critical,
        best_warning=best_warning,
    )
