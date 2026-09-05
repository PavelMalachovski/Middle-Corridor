import type { BasemapId } from "./map/style";

/**
 * Состояние в адресе: груз, вид карты, подложка, момент replay.
 *   /?s=MC-26-0412&view=5.5/43.60/51.20&basemap=dark&at=2026-09-05T12:00:00Z
 * Ссылка открывает тот же груз в том же месте. Без роутера: parse/build —
 * чистые функции, синхронизация через history.replaceState.
 */

export interface MapView {
  zoom: number;
  lat: number;
  lon: number;
}

export interface UrlState {
  s: string | null;
  view: MapView | null;
  basemap: BasemapId | null;
  at: Date | null;
}

const BASEMAPS: BasemapId[] = ["dark", "light", "detailed", "satellite", "custom"];

export function parseView(raw: string | null): MapView | null {
  if (!raw) return null;
  const parts = raw.split("/").map(Number);
  if (parts.length !== 3 || parts.some((n) => !Number.isFinite(n))) return null;
  const [zoom, lat, lon] = parts;
  if (zoom < 0 || zoom > 24 || Math.abs(lat) > 85 || Math.abs(lon) > 180) return null;
  return { zoom, lat, lon };
}

export function formatView(v: MapView): string {
  return `${round(v.zoom, 2)}/${round(v.lat, 4)}/${round(v.lon, 4)}`;
}

function round(n: number, digits: number): number {
  const k = 10 ** digits;
  return Math.round(n * k) / k;
}

export function parseUrlState(search: string): UrlState {
  const q = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  const s = (q.get("s") ?? "").trim().toUpperCase();
  const basemap = q.get("basemap");
  const atRaw = q.get("at");
  const at = atRaw ? new Date(atRaw) : null;
  return {
    s: s ? s : null,
    view: parseView(q.get("view")),
    basemap: basemap && (BASEMAPS as string[]).includes(basemap) ? (basemap as BasemapId) : null,
    at: at && !Number.isNaN(at.getTime()) ? at : null,
  };
}

/** Строка запроса без ведущего «?» (пустая, если состояние по умолчанию). */
export function buildSearch(state: Partial<UrlState>): string {
  const parts: string[] = [];
  // «/» и «:» в query безопасны — оставляем читаемыми: view=5.5/43.6/51.2, at=…T12:00:00Z
  const enc = (v: string) => encodeURIComponent(v).replace(/%2F/g, "/").replace(/%3A/g, ":");
  if (state.s) parts.push(`s=${enc(state.s)}`);
  if (state.view) parts.push(`view=${formatView(state.view)}`);
  if (state.basemap && state.basemap !== "dark") parts.push(`basemap=${enc(state.basemap)}`);
  if (state.at) parts.push(`at=${enc(state.at.toISOString().replace(/\.\d{3}Z$/, "Z"))}`);
  return parts.join("&");
}

/** Одно и то же состояние → одна и та же строка: не дёргать history без изменений. */
export function sameSearch(a: string, b: string): boolean {
  return a.replace(/^\?/, "") === b.replace(/^\?/, "");
}
