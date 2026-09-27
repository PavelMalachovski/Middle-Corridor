"""Сверка предиктора с фактами: эпизоды, POD/FAR/CSI, подбор порогов."""

from datetime import UTC, datetime, timedelta

import pytest

from app.services.calibration import (
    Interval,
    calibrate,
    label_samples,
    merge_episodes,
    score_events,
    score_rule,
)

T0 = datetime(2024, 11, 10, tzinfo=UTC)
NOW = T0 + timedelta(days=30)


def h(hours: float) -> datetime:
    return T0 + timedelta(hours=hours)


def test_escalation_is_one_episode() -> None:
    # warning 0–5 ч, сразу critical 5–9 ч, отдельный алерт через сутки
    alerts = [Interval(h(0), h(5)), Interval(h(5), h(9)), Interval(h(30), h(32))]
    episodes = merge_episodes(alerts, NOW)
    assert episodes == [Interval(h(0), h(9)), Interval(h(30), h(32))]


def test_open_alert_keeps_episode_open() -> None:
    episodes = merge_episodes([Interval(h(0), h(5)), Interval(h(5.5), None)], NOW)
    assert episodes == [Interval(h(0), None)]


def test_hit_miss_and_false_alarm() -> None:
    closures = [
        Interval(h(10), h(20)),  # алерт открыт за 8 ч — попадание
        Interval(h(100), h(110)),  # алертов нет — промах
    ]
    alerts = [
        Interval(h(2), h(21)),
        Interval(h(50), h(55)),  # порт работал — ложная тревога
    ]
    score = score_events(closures, alerts, NOW)
    assert (score.closures, score.hits, score.misses) == (2, 1, 1)
    assert (score.episodes, score.false_alarms) == (2, 1)
    assert score.pod == pytest.approx(0.5)
    assert score.far == pytest.approx(0.5)
    assert score.csi == pytest.approx(1 / 3)
    assert score.median_lead_h == pytest.approx(8.0)


def test_late_alert_within_tolerance_counts_with_zero_lead() -> None:
    # опрос раз в 45 мин: алерт открылся через 40 мин после факта
    score = score_events([Interval(h(10), h(12))], [Interval(h(10.67), h(12))], NOW)
    assert score.hits == 1
    assert score.lead_hours == (0.0,)


def test_alert_that_ended_long_before_is_not_a_hit() -> None:
    # алерт 0–10 ч, остановка в 20 ч: окно попадания [14, 21] — мимо
    score = score_events([Interval(h(20), h(22))], [Interval(h(0), h(10))], NOW)
    assert score.hits == 0
    # но и не ложная тревога: порт встал в пределах grace (10 + 12 ч) после алерта
    assert score.false_alarms == 0


def test_alert_without_closure_within_grace_is_false() -> None:
    score = score_events([Interval(h(30), h(32))], [Interval(h(0), h(10))], NOW)
    assert (score.hits, score.false_alarms) == (0, 1)


def test_empty_period_has_no_ratios() -> None:
    score = score_events([], [], NOW)
    assert score.pod is None and score.far is None and score.csi is None
    assert score.median_lead_h is None


def _synthetic_samples() -> list:
    """Сутки через каждый час: порт стоит, когда ветер ≥ 16 м/с."""
    obs = []
    closures = []
    winds = [8, 9, 12, 14, 16, 18, 20, 17, 15, 11, 9, 7] * 4
    start = None
    for i, w in enumerate(winds):
        ts = h(i)
        obs.append((ts, float(w), float(w) + 5))
        if w >= 16 and start is None:
            start = ts
        if w < 16 and start is not None:
            closures.append(Interval(start, h(i - 1)))
            start = None
    return label_samples(obs, closures, NOW), closures


def test_label_samples_marks_closed_hours() -> None:
    samples, closures = _synthetic_samples()
    assert len(closures) == 4
    assert [s.closed for s in samples[:12]] == [False] * 4 + [True] * 4 + [False] * 4


def test_score_rule_confusion_matrix() -> None:
    samples, _ = _synthetic_samples()
    rule = score_rule(samples, wind=14, gust=100)
    # ветер ≥ 14: 14 (ложная), 16, 18, 20, 17 (попадания), 15 (ложная)
    assert (rule.hits, rule.misses, rule.false_alarms) == (16, 0, 8)
    assert rule.pod == pytest.approx(1.0)
    assert rule.csi == pytest.approx(16 / 24)


def test_calibrate_finds_true_threshold_and_scores_current() -> None:
    samples, closures = _synthetic_samples()
    result = calibrate(samples, closures=len(closures), warning=(13.8, 15.0), critical=(17.0, 21.0))
    assert result.enough_data
    assert result.best_critical is not None
    # идеальное правило: ровно ветер ≥ 16 (порывы = ветер + 5 → gust ≥ 21)
    assert result.best_critical.csi == pytest.approx(1.0)
    assert result.best_critical.false_alarms == 0 and result.best_critical.misses == 0
    assert result.best_warning is not None and (result.best_warning.pod or 0) >= 0.9
    # текущий critical (17 / порывы 21) ловит и 16 м/с через порывы 21
    assert result.current_critical.hits == 16


def test_calibrate_refuses_on_too_few_facts() -> None:
    samples, closures = _synthetic_samples()
    result = calibrate(samples, closures=1, warning=(13.8, 15.0), critical=(17.0, 21.0))
    assert not result.enough_data
    assert result.best_warning is None
    assert result.current_warning.hits > 0  # текущие пороги оцениваются всегда
