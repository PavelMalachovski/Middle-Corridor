import type { WindField } from "../api";

/**
 * Сетка ветра для GPU: из списка точек (lat, lon, speed, dir) — регулярная
 * текстура компонент u (восток) и v (север) в м/с, нормированных в 0..255.
 * Чистые функции — проверяются юнит-тестами без WebGL.
 */

export interface WindGrid {
  lonMin: number;
  latMin: number;
  lonSpan: number;
  latSpan: number;
  cols: number;
  rows: number;
  /** RGBA8, строка 0 — юг (совпадает с v=0 текстуры WebGL). R=u, G=v, A=255 где есть данные. */
  data: Uint8Array;
  uMin: number;
  uMax: number;
  vMin: number;
  vMax: number;
  maxSpeed: number;
}

/** Компоненты скорости: dir — откуда дует, значит поток направлен в dir+180. */
export function windComponents(speed: number, dirFromDeg: number): { u: number; v: number } {
  const to = ((dirFromDeg + 180) * Math.PI) / 180;
  return { u: speed * Math.sin(to), v: speed * Math.cos(to) };
}

export function buildWindGrid(field: WindField): WindGrid | null {
  const step = field.step_deg;
  if (!(step > 0) || field.points.length === 0) return null;
  const cols = Math.round((field.lon_max - field.lon_min) / step) + 1;
  const rows = Math.round((field.lat_max - field.lat_min) / step) + 1;
  if (cols < 2 || rows < 2 || cols * rows > 1_000_000) return null;

  const u = new Float32Array(cols * rows);
  const v = new Float32Array(cols * rows);
  const has = new Uint8Array(cols * rows);
  let uMin = Number.POSITIVE_INFINITY;
  let uMax = Number.NEGATIVE_INFINITY;
  let vMin = Number.POSITIVE_INFINITY;
  let vMax = Number.NEGATIVE_INFINITY;
  let maxSpeed = 0;
  for (const p of field.points) {
    const i = Math.round((p.lon - field.lon_min) / step);
    const j = Math.round((p.lat - field.lat_min) / step);
    if (i < 0 || i >= cols || j < 0 || j >= rows) continue;
    const c = windComponents(p.speed, p.dir);
    const k = j * cols + i;
    u[k] = c.u;
    v[k] = c.v;
    has[k] = 1;
    uMin = Math.min(uMin, c.u);
    uMax = Math.max(uMax, c.u);
    vMin = Math.min(vMin, c.v);
    vMax = Math.max(vMax, c.v);
    maxSpeed = Math.max(maxSpeed, p.speed);
  }
  if (!Number.isFinite(uMin)) return null;
  // ноль всегда внутри диапазона: пропуски кодируются как штиль без переполнения
  uMin = Math.min(uMin, 0);
  uMax = Math.max(uMax, 0);
  vMin = Math.min(vMin, 0);
  vMax = Math.max(vMax, 0);
  // вырожденный диапазон (штиль везде) — чтобы деление не дало NaN
  if (uMax - uMin < 1e-6) uMax = uMin + 1e-6;
  if (vMax - vMin < 1e-6) vMax = vMin + 1e-6;
  const byte = (x: number, lo: number, hi: number) =>
    Math.max(0, Math.min(255, Math.round(((x - lo) / (hi - lo)) * 255)));

  const data = new Uint8Array(cols * rows * 4);
  for (let k = 0; k < cols * rows; k++) {
    const o = k * 4;
    if (!has[k]) {
      // нет данных: ровно нулевая скорость и alpha 0 (шейдер гасит частицу)
      data[o] = byte(0, uMin, uMax);
      data[o + 1] = byte(0, vMin, vMax);
      data[o + 3] = 0;
      continue;
    }
    data[o] = byte(u[k], uMin, uMax);
    data[o + 1] = byte(v[k], vMin, vMax);
    data[o + 2] = 0;
    data[o + 3] = 255;
  }
  return {
    lonMin: field.lon_min,
    latMin: field.lat_min,
    lonSpan: (cols - 1) * step,
    latSpan: (rows - 1) * step,
    cols,
    rows,
    data,
    uMin,
    uMax,
    vMin,
    vMax,
    maxSpeed,
  };
}

/**
 * Уровень детализации точки сетки для стрелок: 4 — каждая четвёртая по обеим
 * осям, 2 — каждая вторая, 1 — все. Слои стрелок фильтруют по зуму, чтобы на
 * мелком масштабе не было сплошной сетки.
 */
export function windLod(field: WindField, lon: number, lat: number): 1 | 2 | 4 {
  const i = Math.round((lon - field.lon_min) / field.step_deg);
  const j = Math.round((lat - field.lat_min) / field.step_deg);
  if (i % 4 === 0 && j % 4 === 0) return 4;
  if (i % 2 === 0 && j % 2 === 0) return 2;
  return 1;
}

/** Цветовая шкала → 256 RGBA-пикселей для текстуры 16×16. */
export function colorRamp(colors: string[]): Uint8Array {
  const rgb = colors.map(hexToRgb);
  const out = new Uint8Array(256 * 4);
  for (let i = 0; i < 256; i++) {
    const t = (i / 255) * (rgb.length - 1);
    const a = Math.min(Math.floor(t), rgb.length - 2);
    const f = t - a;
    for (let c = 0; c < 3; c++)
      out[i * 4 + c] = Math.round(rgb[a][c] + (rgb[a + 1][c] - rgb[a][c]) * f);
    out[i * 4 + 3] = 255;
  }
  return out;
}

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  const n = Number.parseInt(h.length === 3 ? h.replace(/./g, (ch) => ch + ch) : h, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
