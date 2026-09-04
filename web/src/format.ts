import type { AlertLevel, NodeStatus, ShipmentState, Thresholds } from "./api";

const RU_DATE = new Intl.DateTimeFormat("ru-RU", {
  day: "2-digit",
  month: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "UTC",
});

export function fmtTs(iso: string | null | undefined): string {
  if (!iso) return "—";
  return `${RU_DATE.format(new Date(iso))} UTC`;
}

/** «5 мин назад» / «через 3 ч» относительно опорного момента (generated_at). */
export function fmtRelative(iso: string | null | undefined, ref: Date): string {
  if (!iso) return "—";
  const diffMin = Math.round((new Date(iso).getTime() - ref.getTime()) / 60000);
  const abs = Math.abs(diffMin);
  const past = diffMin < 0;
  let body: string;
  if (abs < 1) body = "сейчас";
  else if (abs < 60) body = `${abs} мин`;
  else if (abs < 48 * 60) body = `${Math.round(abs / 60)} ч`;
  else body = `${Math.round(abs / 1440)} дн`;
  if (body === "сейчас") return body;
  return past ? `${body} назад` : `через ${body}`;
}

export function fmtHours(hours: number): string {
  if (hours < 1) return "< 1 ч";
  if (hours < 48) return `${Math.round(hours)} ч`;
  const days = Math.floor(hours / 24);
  const rest = Math.round(hours - days * 24);
  return rest ? `${days} дн ${rest} ч` : `${days} дн`;
}

export function fmtWind(speed: number | null, gust: number | null): string {
  if (speed == null) return "нет данных";
  const base = `${speed.toFixed(0)} м/с`;
  return gust != null ? `${base}, порывы ${gust.toFixed(0)}` : base;
}

const COMPASS = ["С", "СВ", "В", "ЮВ", "Ю", "ЮЗ", "З", "СЗ"];
export function fmtDir(deg: number | null): string {
  if (deg == null) return "";
  return COMPASS[Math.round(deg / 45) % 8];
}

export const STATE_LABEL: Record<ShipmentState, string> = {
  planned: "Ожидает отправления",
  in_transit: "В пути",
  waiting: "Стоянка",
  delivered: "Доставлен",
};

export const LEVEL_LABEL: Record<AlertLevel, string> = {
  watch: "усиление ветра",
  warning: "риск остановки",
  critical: "вероятна остановка",
};

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

export const REPORT_TITLE: Record<string, string> = {
  queue: "Очередь в порту",
  rate: "Ставка",
  border_delay: "Простой на границе",
  note: "Заметка",
};

export const PAYLOAD_LABEL: Record<string, string> = {
  vessels_waiting: "Судов в ожидании",
  ferry_expected: "Паром ожидается",
  rate_usd: "Ставка, USD",
  delay_hours: "Простой, ч",
  border: "Граница",
};
