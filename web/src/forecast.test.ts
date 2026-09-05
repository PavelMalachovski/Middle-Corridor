import { describe, expect, it } from "vitest";
import type { Shipment, Thresholds, WindHour } from "./api";
import { checkpointDelays, fmtIn, portOutlook } from "./forecast";

const T: Thresholds = {
  watch_wind: 10,
  warning_wind: 14,
  warning_gust: 20,
  critical_wind: 18,
  critical_gust: 25,
};
const NOW = new Date("2026-09-05T12:00:00Z");
const hour = (h: number, speed: number, gust = speed + 4): WindHour => ({
  ts: new Date(NOW.getTime() + h * 3_600_000).toISOString(),
  speed,
  gust,
  level: null,
});

describe("portOutlook", () => {
  it("спокойно — остановки нет, пик найден", () => {
    const o = portOutlook([hour(0, 5), hour(1, 7), hour(2, 6)], T, NOW);
    expect(o.closedNow).toBe(false);
    expect(o.stopsAt).toBeNull();
    expect(o.opensAt).toBeNull();
    expect(o.peak?.speed).toBe(7);
  });
  it("шторм через 3 часа, открытие, когда ветер ниже warning", () => {
    const f = [
      hour(0, 8),
      hour(1, 12),
      hour(2, 15),
      hour(3, 19),
      hour(4, 20),
      hour(5, 15),
      hour(6, 12),
    ];
    const o = portOutlook(f, T, NOW);
    expect(o.closedNow).toBe(false);
    expect(o.stopsAt).toBe(hour(3, 0).ts);
    expect(o.opensAt).toBe(hour(6, 0).ts); // 15 м/с — ещё warning, 12 — уже нет
  });
  it("порт закрыт сейчас — stopsAt = текущий час", () => {
    const o = portOutlook([hour(0, 21), hour(1, 19), hour(2, 9)], T, NOW);
    expect(o.closedNow).toBe(true);
    expect(o.stopsAt).toBe(hour(0, 0).ts);
    expect(o.opensAt).toBe(hour(2, 0).ts);
  });
  it("прошлые часы не считаются, уровень с бэкенда важнее порогов", () => {
    const f = [hour(-3, 30), { ...hour(1, 5), level: "critical" as const }];
    const o = portOutlook(f, T, NOW);
    expect(o.stopsAt).toBe(hour(1, 0).ts);
  });
});

describe("checkpointDelays", () => {
  it("факт минус план, будущие — по текущей задержке", () => {
    const s = {
      delay_hours: 6,
      checkpoints: [
        {
          code: "A",
          name: "A",
          planned_at: "2026-09-01T00:00:00Z",
          actual_at: "2026-09-01T02:30:00Z",
        },
        { code: "B", name: "B", planned_at: "2026-09-02T00:00:00Z", actual_at: null },
      ],
    } as unknown as Shipment;
    expect(checkpointDelays(s)).toEqual([
      { code: "A", name: "A", hours: 2.5, projected: false },
      { code: "B", name: "B", hours: 6, projected: true },
    ]);
  });
});

describe("fmtIn", () => {
  it("минуты, часы, сейчас", () => {
    expect(fmtIn(hour(0, 0).ts, NOW)).toBe("сейчас");
    expect(fmtIn(new Date(NOW.getTime() + 40 * 60_000).toISOString(), NOW)).toBe("через 40 мин");
    expect(fmtIn(hour(5, 0).ts, NOW)).toBe("через 5 ч");
  });
});
