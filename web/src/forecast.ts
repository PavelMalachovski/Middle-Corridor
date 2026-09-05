import type { AlertLevel, Checkpoint, Shipment, Thresholds, WindHour } from "./api";
import { levelForWind } from "./format";
import { t } from "./i18n";

/**
 * Чистая логика прогноза и задержек для графиков — без React, под юнит-тесты.
 */

export interface Outlook {
  /** Сейчас порт закрыт (критический ветер) */
  closedNow: boolean;
  /** Ближайший час, когда ветер станет критическим (порт встанет); null — в окне не ожидается */
  stopsAt: string | null;
  /** Час, когда ветер опустится ниже warning после остановки (порт откроется) */
  opensAt: string | null;
  /** Пик ветра в окне прогноза */
  peak: WindHour | null;
}

const HOUR_MS = 3_600_000;

function levelRank(level: AlertLevel | "ok" | null | undefined): number {
  switch (level) {
    case "critical":
      return 3;
    case "warning":
      return 2;
    case "watch":
      return 1;
    default:
      return 0;
  }
}

/** Уровень часа: с бэкенда, а если его нет — по порогам. */
export function hourLevel(h: WindHour, t: Thresholds): AlertLevel | "ok" {
  return h.level ?? levelForWind(h.speed, h.gust, t);
}

/**
 * Когда порт встанет и когда откроется. Смотрим только будущее (ts >= now):
 * остановка — первый час с critical, открытие — первый час после него ниже warning.
 */
export function portOutlook(forecast: WindHour[], t: Thresholds, now: Date): Outlook {
  const future = forecast.filter((h) => Date.parse(h.ts) >= now.getTime() - HOUR_MS / 2);
  const current = future[0] ?? null;
  const closedNow = current != null && levelRank(hourLevel(current, t)) >= 3;
  let stopsAt: string | null = null;
  let opensAt: string | null = null;
  let peak: WindHour | null = null;
  let i = 0;
  if (closedNow) {
    stopsAt = current.ts;
  } else {
    i = future.findIndex((h) => levelRank(hourLevel(h, t)) >= 3);
    stopsAt = i >= 0 ? future[i].ts : null;
  }
  if (stopsAt != null) {
    const start = Math.max(i, 0);
    const open = future.slice(start).find((h) => levelRank(hourLevel(h, t)) < 2);
    opensAt = open?.ts ?? null;
  }
  for (const h of future) if (!peak || h.speed > peak.speed) peak = h;
  return { closedNow, stopsAt, opensAt, peak };
}

export interface CheckpointDelay {
  code: string;
  name: string;
  /** Отклонение от плана, ч: > 0 — опоздание; для будущих узлов — прогноз по текущей задержке */
  hours: number;
  projected: boolean;
}

/** Задержка по чекпоинтам: факт − план, для непройденных — текущая задержка груза. */
export function checkpointDelays(s: Shipment): CheckpointDelay[] {
  return s.checkpoints.map((cp: Checkpoint) => {
    if (cp.actual_at) {
      const hours = (Date.parse(cp.actual_at) - Date.parse(cp.planned_at)) / HOUR_MS;
      return { code: cp.code, name: cp.name, hours: Math.round(hours * 10) / 10, projected: false };
    }
    return {
      code: cp.code,
      name: cp.name,
      hours: Math.round(s.delay_hours * 10) / 10,
      projected: true,
    };
  });
}

/** «через 5 ч», «через 40 мин», «сейчас» */
export function fmtIn(iso: string, now: Date): string {
  const min = Math.round((Date.parse(iso) - now.getTime()) / 60_000);
  if (min <= 0) return t("common.now");
  if (min < 60) return t("common.in", { value: `${min} ${t("common.min")}` });
  return t("common.in", { value: `${Math.round(min / 60)} ${t("common.h")}` });
}
