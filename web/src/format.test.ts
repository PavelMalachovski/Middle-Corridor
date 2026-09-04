import { describe, expect, it } from "vitest";
import type { NodeStatus, Thresholds } from "./api";
import {
  findNearestNode,
  fmtDir,
  fmtHours,
  fmtRelative,
  fmtTs,
  fmtWind,
  levelForWind,
  levelOf,
} from "./format";

const REF = new Date("2026-09-04T12:00:00Z");

describe("fmtTs", () => {
  it("день.месяц, часы:минуты в UTC", () => {
    const s = fmtTs("2026-09-04T12:05:00Z");
    expect(s).toContain("04.09");
    expect(s).toContain("12:05");
    expect(s.endsWith("UTC")).toBe(true);
    expect(fmtTs(null)).toBe("—");
  });
});

describe("fmtRelative", () => {
  it("минуты, часы, дни; прошлое и будущее", () => {
    expect(fmtRelative("2026-09-04T11:55:00Z", REF)).toBe("5 мин назад");
    expect(fmtRelative("2026-09-04T15:00:00Z", REF)).toBe("через 3 ч");
    expect(fmtRelative("2026-09-01T12:00:00Z", REF)).toBe("3 дн назад");
    expect(fmtRelative("2026-09-04T12:00:20Z", REF)).toBe("сейчас");
    expect(fmtRelative(undefined, REF)).toBe("—");
  });
  it("до двух суток считает в часах", () => {
    expect(fmtRelative("2026-09-06T06:00:00Z", REF)).toBe("через 42 ч");
  });
});

describe("fmtHours / fmtWind / fmtDir", () => {
  it("часы и дни задержки", () => {
    expect(fmtHours(0.5)).toBe("< 1 ч");
    expect(fmtHours(17.6)).toBe("18 ч");
    expect(fmtHours(48)).toBe("2 дн");
    expect(fmtHours(51)).toBe("2 дн 3 ч");
  });
  it("ветер с порывами и без данных", () => {
    expect(fmtWind(12.4, 18.6)).toBe("12 м/с, порывы 19");
    expect(fmtWind(7.2, null)).toBe("7 м/с");
    expect(fmtWind(null, null)).toBe("нет данных");
  });
  it("румбы по 45°, 359° — снова север", () => {
    expect(fmtDir(0)).toBe("С");
    expect(fmtDir(45)).toBe("СВ");
    expect(fmtDir(180)).toBe("Ю");
    expect(fmtDir(270)).toBe("З");
    expect(fmtDir(359)).toBe("С");
    expect(fmtDir(null)).toBe("");
  });
});

const T = {
  watch_wind: 10,
  warning_wind: 14,
  warning_gust: 20,
  critical_wind: 18,
  critical_gust: 25,
} as unknown as Thresholds;

describe("levelForWind", () => {
  it("пороги по скорости и порывам", () => {
    expect(levelForWind(5, 8, T)).toBe("ok");
    expect(levelForWind(10, 12, T)).toBe("watch");
    expect(levelForWind(14, 15, T)).toBe("warning");
    expect(levelForWind(9, 21, T)).toBe("warning"); // порыв тянет уровень
    expect(levelForWind(18, 0, T)).toBe("critical");
    expect(levelForWind(12, 25, T)).toBe("critical");
  });
});

const node = (over: Partial<NodeStatus>): NodeStatus =>
  ({
    code: "X",
    name: "X",
    lat: 0,
    lon: 0,
    is_weather_tracked: true,
    alert_level: null,
    wind_speed: 5,
    ...over,
  }) as NodeStatus;

describe("levelOf", () => {
  it("без погоды — none, с погодой без алерта — ok", () => {
    expect(levelOf(node({ is_weather_tracked: false }))).toBe("none");
    expect(levelOf(node({ wind_speed: null }))).toBe("none");
    expect(levelOf(node({}))).toBe("ok");
    expect(levelOf(node({ alert_level: "critical" }))).toBe("critical");
  });
});

describe("findNearestNode", () => {
  const aktau = node({ code: "AKTAU", lat: 43.65, lon: 51.2 });
  const baku = node({ code: "BAKU", lat: 40.4, lon: 49.87 });
  const rail = node({ code: "RAIL", lat: 42.0, lon: 50.5, is_weather_tracked: false });

  it("ближайший порт с погодой, узлы без погоды пропускаются", () => {
    expect(findNearestNode([aktau, baku, rail], 42.0, 50.5)?.code).toBe("BAKU");
    expect(findNearestNode([aktau, baku, rail], 42.0, 50.5, false)?.code).toBe("RAIL");
  });
  it("пустой список — null", () => {
    expect(findNearestNode([], 0, 0)).toBeNull();
    expect(findNearestNode([rail], 42, 50.5)).toBeNull();
  });
});
