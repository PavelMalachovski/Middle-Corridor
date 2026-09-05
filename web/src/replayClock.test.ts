import { describe, expect, it } from "vitest";
import {
  clampToWindow,
  EDGE_MARGIN_MS,
  estimateServerNow,
  fmtOffset,
  HOUR_MS,
  offsetHours,
} from "./replayClock";

const WIN = { pastHours: 72, futureHours: 24 };
const NOW = Date.UTC(2026, 8, 4, 12, 0, 0);

describe("estimateServerNow", () => {
  it("прибавляет к серверной опоре прошедшее у клиента время", () => {
    const clock = { serverMs: 1_000_000, wallMs: 5_000 };
    expect(estimateServerNow(clock, 5_000)).toBe(1_000_000);
    expect(estimateServerNow(clock, 8_000)).toBe(1_003_000);
  });
  it("ускоренные часы мока: прошедшее время умножается на scale", () => {
    const clock = { serverMs: 1_000_000, wallMs: 5_000, scale: 600 };
    expect(estimateServerNow(clock, 6_000)).toBe(1_600_000);
  });
});

describe("clampToWindow", () => {
  it("оставляет момент внутри окна как есть", () => {
    const at = NOW - 10 * HOUR_MS;
    expect(clampToWindow(at, NOW, WIN)).toBe(at);
  });
  it("прижимает к краям с отступом", () => {
    expect(clampToWindow(NOW - 1000 * HOUR_MS, NOW, WIN)).toBe(NOW - 72 * HOUR_MS + EDGE_MARGIN_MS);
    expect(clampToWindow(NOW + 1000 * HOUR_MS, NOW, WIN)).toBe(NOW + 24 * HOUR_MS - EDGE_MARGIN_MS);
  });
  it("бесконечность даёт верхний край — так останавливается воспроизведение", () => {
    expect(clampToWindow(Number.POSITIVE_INFINITY, NOW, WIN)).toBe(
      NOW + 24 * HOUR_MS - EDGE_MARGIN_MS,
    );
  });
});

describe("offsetHours", () => {
  it("считает смещение в часах со знаком", () => {
    expect(offsetHours(NOW - 6 * HOUR_MS, NOW)).toBe(-6);
    expect(offsetHours(NOW + 90 * 60_000, NOW)).toBe(1.5);
  });
});

describe("fmtOffset", () => {
  it("минуты до часа, часы до двух суток, дальше дни", () => {
    expect(fmtOffset(-0.5)).toBe("−30 мин");
    expect(fmtOffset(-6)).toBe("−6 ч");
    expect(fmtOffset(1.5)).toBe("+1.5 ч");
    expect(fmtOffset(-30)).toBe("−30 ч");
    expect(fmtOffset(60)).toBe("+2.5 дн");
    expect(fmtOffset(-72)).toBe("−3 дн");
  });
  it("использует типографский минус, а не дефис", () => {
    expect(fmtOffset(-2).startsWith("−")).toBe(true);
    expect(fmtOffset(-2).includes("-")).toBe(false);
  });
});
