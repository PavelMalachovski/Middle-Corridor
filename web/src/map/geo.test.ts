import { describe, expect, it } from "vitest";
import { haversineKm, type LonLat, splitTrack } from "./geo";

const AKTAU: LonLat = [51.2, 43.65];
const BAKU: LonLat = [49.87, 40.4];
const POTI: LonLat = [41.67, 42.15];

describe("haversineKm", () => {
  it("Актау — Баку около 380 км", () => {
    const d = haversineKm(AKTAU, BAKU);
    expect(d).toBeGreaterThan(350);
    expect(d).toBeLessThan(410);
  });
  it("симметрична и нулевая для одной точки", () => {
    expect(haversineKm(AKTAU, BAKU)).toBeCloseTo(haversineKm(BAKU, AKTAU), 9);
    expect(haversineKm(POTI, POTI)).toBe(0);
  });
});

describe("splitTrack", () => {
  const track: LonLat[] = [AKTAU, BAKU, POTI];

  it("половина пути делит трек по длине, а не по числу точек", () => {
    const { done, rest } = splitTrack(track, 0.5);
    const total = haversineKm(AKTAU, BAKU) + haversineKm(BAKU, POTI);
    const doneKm = done.slice(1).reduce((acc, p, i) => acc + haversineKm(done[i], p), 0);
    // точка разрыва интерполируется линейно по lon/lat, поэтому допуск — 1 % длины
    expect(Math.abs(doneKm - total / 2)).toBeLessThan(total * 0.01);
    // точка разрыва общая для обеих частей
    expect(rest[0]).toEqual(done[done.length - 1]);
    expect(rest[rest.length - 1]).toEqual(POTI);
  });

  it("0 — всё впереди, 1 — всё пройдено", () => {
    const start = splitTrack(track, 0);
    expect(start.done).toEqual([AKTAU, AKTAU]); // вырожденный отрезок — линии нет
    expect(start.rest).toEqual([AKTAU, BAKU, POTI]);
    const end = splitTrack(track, 1);
    expect(end.done).toEqual([AKTAU, BAKU, POTI]);
    // остаток вырождается в точку финиша — линии из него не выйдет
    expect(end.rest.every((p) => p[0] === POTI[0] && p[1] === POTI[1])).toBe(true);
  });

  it("доля вне 0..1 обрезается", () => {
    expect(splitTrack(track, -3).done).toEqual(splitTrack(track, 0).done);
    expect(splitTrack(track, 7).done).toEqual(splitTrack(track, 1).done);
  });

  it("одна точка или пусто — без деления", () => {
    expect(splitTrack([AKTAU], 0.5)).toEqual({ done: [AKTAU], rest: [] });
    expect(splitTrack([], 0.5)).toEqual({ done: [], rest: [] });
  });
});
