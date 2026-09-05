import type { NodeStatus, ReportStatus, Shipment, VesselStatus } from "../api";
import { getLang, type Key, type Lang, nodeNameByCode, translate } from "./index";

/**
 * Тексты из данных бэкенда на текущем языке. Бэкенд отдаёт коды (событие,
 * причина стоянки, фаза судна) и русские строки для бота; здесь коды
 * превращаются в подписи, а без кода остаётся русская строка как есть.
 */

const NOTE_CODES = new Set(["loaded_on_ferry", "loaded_on_vessel", "gauge_change_done"]);
const HOLD_CODES = new Set([
  "weather_ban",
  "customs_wait",
  "ferry_loading_wait",
  "ferry_return_wait",
]);

export function eventLabel(s: Shipment, nodes: NodeStatus[], lang: Lang = getLang()): string {
  if (!s.last_event_kind) return lang === "ru" ? s.last_event : translate(lang, "event.none");
  if (lang === "ru" && !s.last_event_note_code) return s.last_event; // бэкенд уже собрал строку
  const node = nodeNameByCode(nodes, s.last_event_node, lang);
  const base = translate(lang, `event.${s.last_event_kind}` as Key, { node });
  const code = s.last_event_note_code;
  if (code && NOTE_CODES.has(code)) {
    const note = translate(lang, `note.${code}` as Key, { vessel: s.last_event_note_vessel ?? "" });
    return `${base} — ${note}`;
  }
  return lang === "ru" ? s.last_event : base;
}

export function holdLabel(s: Shipment, nodes: NodeStatus[], lang: Lang = getLang()): string | null {
  if (!s.hold_reason && !s.hold_code) return null;
  const code = s.hold_code;
  if (code && HOLD_CODES.has(code)) {
    return translate(lang, `hold.${code}` as Key, {
      node: nodeNameByCode(nodes, s.hold_node, lang),
      vessel: s.hold_vessel ?? "",
    });
  }
  return s.hold_reason;
}

/** Текст алерта по ветру строим сами: числа есть в узле на любом языке. */
export function alertText(node: NodeStatus, lang: Lang = getLang()): string | null {
  if (!node.alert_level || node.wind_speed == null) return null;
  return translate(lang, "alert.wind", {
    speed: node.wind_speed.toFixed(0),
    gust: (node.wind_gust ?? node.wind_speed).toFixed(0),
  });
}

export function vesselRoute(
  v: VesselStatus,
  nodes: NodeStatus[],
  lang: Lang = getLang(),
): string | null {
  if (v.from_code && v.to_code) {
    return `${nodeNameByCode(nodes, v.from_code, lang)} → ${nodeNameByCode(nodes, v.to_code, lang)}`;
  }
  return v.route ?? null;
}

export function vesselPhase(
  v: VesselStatus,
  nodes: NodeStatus[],
  lang: Lang = getLang(),
): string | null {
  if (v.phase_code === "at_sea") return translate(lang, "vessel.atSea");
  if (v.phase_code === "in_port") {
    return translate(lang, "vessel.inPort", { node: nodeNameByCode(nodes, v.phase_node, lang) });
  }
  return v.phase ?? null;
}

export function reportPort(
  r: ReportStatus,
  nodes: NodeStatus[],
  lang: Lang = getLang(),
): string | null {
  if (r.port_code) return nodeNameByCode(nodes, r.port_code, lang);
  return r.port_name ?? null;
}
