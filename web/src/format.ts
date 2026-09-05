import type { AlertLevel, NodeStatus, ShipmentState, Thresholds } from "./api";
import { getLang, type Key, type Lang, t } from "./i18n";

/**
 * Форматтеры дат, длительностей и подписей. Язык берут из модуля i18n
 * (getLang) — компоненты перерисовываются провайдером, поэтому вызов из
 * рендера всегда даёт актуальный язык; в тестах по умолчанию русский.
 */

const DATE_FMT: Record<Lang, Intl.DateTimeFormat> = {
  ru: new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  }),
  en: new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  }),
};

export function fmtTs(iso: string | null | undefined): string {
  if (!iso) return "—";
  return `${DATE_FMT[getLang()].format(new Date(iso))} UTC`;
}

/** «5 мин назад» / «через 3 ч» относительно опорного момента (generated_at). */
export function fmtRelative(iso: string | null | undefined, ref: Date): string {
  if (!iso) return "—";
  const diffMin = Math.round((new Date(iso).getTime() - ref.getTime()) / 60000);
  const abs = Math.abs(diffMin);
  const past = diffMin < 0;
  let body: string;
  if (abs < 1) return t("common.now");
  if (abs < 60) body = `${abs} ${t("common.min")}`;
  else if (abs < 48 * 60) body = `${Math.round(abs / 60)} ${t("common.h")}`;
  else body = `${Math.round(abs / 1440)} ${t("common.d")}`;
  return past ? t("common.ago", { value: body }) : t("common.in", { value: body });
}

export function fmtHours(hours: number): string {
  if (hours < 1) return t("common.lessThanHour");
  if (hours < 48) return `${Math.round(hours)} ${t("common.h")}`;
  const days = Math.floor(hours / 24);
  const rest = Math.round(hours - days * 24);
  return rest ? t("common.daysHours", { days, hours: rest }) : t("common.days", { days });
}

export function fmtWind(speed: number | null, gust: number | null): string {
  if (speed == null) return t("common.noData");
  const base = `${speed.toFixed(0)} ${t("common.ms")}`;
  return gust != null ? `${base}, ${gustWord()} ${gust.toFixed(0)}` : base;
}

function gustWord(): string {
  return getLang() === "en" ? "gusts" : "порывы";
}

const COMPASS: Record<Lang, string[]> = {
  ru: ["С", "СВ", "В", "ЮВ", "Ю", "ЮЗ", "З", "СЗ"],
  en: ["N", "NE", "E", "SE", "S", "SW", "W", "NW"],
};
export function fmtDir(deg: number | null): string {
  if (deg == null) return "";
  return COMPASS[getLang()][Math.round(deg / 45) % 8];
}

export function stateLabel(state: ShipmentState): string {
  return t(`state.${state}` as Key);
}

export function levelLabel(level: AlertLevel): string {
  return t(`level.${level}` as Key);
}

export const LEVEL_ICON: Record<AlertLevel, string> = {
  watch: "◔",
  warning: "▲",
  critical: "●",
};

/** Статусные цвета из палитры dataviz — всегда вместе с иконкой и подписью. */
export const LEVEL_COLOR: Record<AlertLevel | "ok" | "none", string> = {
  none: "#6b6b66",
  ok: "#0ca30c",
  watch: "#fab219",
  warning: "#ec835a",
  critical: "#d03b3b",
};

export function levelOf(node: NodeStatus): AlertLevel | "ok" | "none" {
  if (!node.is_weather_tracked || node.wind_speed == null) return "none";
  return node.alert_level ?? "ok";
}

export function levelForWind(speed: number, gust: number, t: Thresholds): AlertLevel | "ok" {
  if (speed >= t.critical_wind || gust >= t.critical_gust) return "critical";
  if (speed >= t.warning_wind || gust >= t.warning_gust) return "warning";
  if (speed >= t.watch_wind) return "watch";
  return "ok";
}

export function findNearestNode(
  nodes: NodeStatus[],
  lat: number,
  lon: number,
  onlyWeather = true,
): NodeStatus | null {
  let best: NodeStatus | null = null;
  let bestD = Infinity;
  for (const node of nodes) {
    if (onlyWeather && !node.is_weather_tracked) continue;
    const dLat = node.lat - lat;
    const dLon = (node.lon - lon) * Math.cos((lat * Math.PI) / 180);
    const d = dLat * dLat + dLon * dLon;
    if (d < bestD) {
      bestD = d;
      best = node;
    }
  }
  return best;
}

const REPORT_KEYS = new Set(["queue", "rate", "border_delay", "note"]);
export function reportTitle(type: string): string {
  return REPORT_KEYS.has(type) ? t(`report.${type}` as Key) : type;
}

const PAYLOAD_KEYS = new Set([
  "vessels_waiting",
  "ferry_expected",
  "rate_usd",
  "delay_hours",
  "border",
]);
export function payloadLabel(key: string): string {
  return PAYLOAD_KEYS.has(key) ? t(`payload.${key}` as Key) : key;
}
