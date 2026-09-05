import { describe, expect, it } from "vitest";
import type { WindField } from "../api";
import { buildWindGrid, colorRamp, windComponents, windLod } from "./windGrid";

const field = (points: WindField["points"], step = 1): WindField => ({
  ts: "2026-09-04T12:00:00Z",
  lat_min: 40,
  lon_min: 50,
  lat_max: 42,
  lon_max: 53,
  step_deg: step,
  points,
});

describe("windComponents", () => {
  it("dir — откуда дует: северный ветер (0°) несёт на юг", () => {
    const n = windComponents(10, 0);
    expect(n.u).toBeCloseTo(0, 6);
    expect(n.v).toBeCloseTo(-10, 6);
    const w = windComponents(5, 270); // западный → на восток
    expect(w.u).toBeCloseTo(5, 6);
    expect(w.v).toBeCloseTo(0, 6);
  });
});

describe("buildWindGrid", () => {
  it("раскладывает точки по регулярной сетке, строка 0 — юг", () => {
    const pts: WindField["points"] = [];
    for (let lat = 40; lat <= 42; lat++)
      for (let lon = 50; lon <= 53; lon++)
        pts.push({ lat, lon, speed: lat === 40 ? 10 : 2, gust: 0, dir: 270 });
    const g = buildWindGrid(field(pts));
    expect(g).not.toBeNull();
    expect([g!.cols, g!.rows]).toEqual([4, 3]);
    expect([g!.lonSpan, g!.latSpan]).toEqual([3, 2]);
    expect(g!.maxSpeed).toBe(10);
    // южная строка (lat 40) — u=10 = максимум шкалы → 255; северная — u=2 → ниже
    expect(g!.data[0]).toBe(255);
    expect(g!.data[2 * 4 * 4]).toBeLessThan(255);
    expect(g!.data[3]).toBe(255); // alpha = есть данные
  });

  it("пропуски помечаются alpha 0 и кодируют нулевую скорость", () => {
    const g = buildWindGrid(field([{ lat: 40, lon: 50, speed: 8, gust: 0, dir: 90 }]));
    expect(g).not.toBeNull();
    const last = (g!.cols * g!.rows - 1) * 4;
    expect(g!.data[last + 3]).toBe(0);
    const u = (g!.data[last] / 255) * (g!.uMax - g!.uMin) + g!.uMin;
    expect(Math.abs(u)).toBeLessThan(0.1);
  });

  it("пустое поле или нулевой шаг — null", () => {
    expect(buildWindGrid(field([]))).toBeNull();
    expect(buildWindGrid(field([{ lat: 40, lon: 50, speed: 1, gust: 0, dir: 0 }], 0))).toBeNull();
  });
});

describe("windLod", () => {
  it("каждая четвёртая/вторая точка от начала сетки", () => {
    const f = field([]);
    expect(windLod(f, 50, 40)).toBe(4);
    expect(windLod(f, 52, 42)).toBe(2);
    expect(windLod(f, 51, 40)).toBe(1);
    expect(windLod(f, 54, 44)).toBe(4);
  });
});

describe("colorRamp", () => {
  it("256 пикселей от первого цвета к последнему", () => {
    const r = colorRamp(["#000000", "#ffffff"]);
    expect(r.length).toBe(1024);
    expect([r[0], r[1], r[2], r[3]]).toEqual([0, 0, 0, 255]);
    expect([r[1020], r[1021], r[1022]]).toEqual([255, 255, 255]);
    expect(r[128 * 4]).toBeGreaterThan(120);
    expect(r[128 * 4]).toBeLessThan(136);
  });
});
