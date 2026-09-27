import { describe, expect, it } from "vitest";
import { type Box, declutter, type LabelItem, overlaps } from "./declutter";

const box = (x: number, y: number, w = 40, h = 12): Box => ({ x, y, w, h });
const item = (id: string, priority: number, ...candidates: Box[]): LabelItem => ({
  id,
  priority,
  candidates,
});

describe("overlaps", () => {
  it("касание по краю — не пересечение, отступ расширяет", () => {
    expect(overlaps(box(0, 0), box(40, 0))).toBe(false);
    expect(overlaps(box(0, 0), box(41, 0), 2)).toBe(true);
    expect(overlaps(box(0, 0), box(10, 5))).toBe(true);
  });
});

describe("declutter", () => {
  it("из двух налезающих подписей без запасного места прячет менее важную", () => {
    const placed = declutter([item("vessel", 45, box(10, 4)), item("port", 75, box(0, 0))]);
    expect(placed.get("port")).toBe(0);
    expect(placed.get("vessel")).toBe(-1);
  });

  it("не налезающие подписи остаются на своих местах", () => {
    const placed = declutter([
      item("a", 1, box(0, 0)),
      item("b", 1, box(0, 30)),
      item("c", 1, box(100, 0)),
    ]);
    expect([...placed.values()]).toEqual([0, 0, 0]);
  });

  it("тесно справа — подпись переезжает налево", () => {
    const placed = declutter([
      item("port", 75, box(0, 0)),
      item("cargo", 55, box(10, 2), box(-60, 2)), // справа занято портом, слева свободно
    ]);
    expect(placed.get("cargo")).toBe(1);
  });

  it("спрятанная подпись не мешает следующей", () => {
    // a важнее всех; b налезает на a и прячется; c налезает только на b — остаётся
    const placed = declutter([
      item("a", 3, box(0, 0)),
      item("b", 2, box(30, 0)),
      item("c", 1, box(60, 0)),
    ]);
    expect(placed.get("b")).toBe(-1);
    expect(placed.get("c")).toBe(0);
  });

  it("точка более важного маркера — препятствие, менее важного — нет", () => {
    const items: LabelItem[] = [
      { ...item("port", 75, box(200, 0)), anchor: box(20, 2, 10, 10) },
      { ...item("cargo", 55, box(0, 0)), anchor: box(300, 0, 10, 10) },
      { ...item("delivered", 30, box(295, 0)), anchor: box(500, 0, 10, 10) },
      { ...item("big", 80, box(295, 2)), anchor: box(600, 0, 10, 10) },
    ];
    const placed = declutter(items);
    expect(placed.get("cargo")).toBe(-1); // лежит на точке порта
    expect(placed.get("delivered")).toBe(-1); // лежит на точке груза (важнее)
    expect(placed.get("big")).toBe(0); // на точку менее важного груза — можно
  });

  it("сторона без чужих точек лучше, даже если справа мешает лишь менее важный маркер", () => {
    const items: LabelItem[] = [
      { ...item("port", 75, box(10, 0), box(-50, 0)), anchor: box(0, 2, 8, 8) },
      { ...item("ferry", 45, box(500, 0)), anchor: box(20, 2, 8, 8) }, // стоит на подписи справа
    ];
    expect(declutter(items).get("port")).toBe(1);
  });

  it("равный приоритет — детерминированно по id", () => {
    const placed = declutter([item("b", 5, box(5, 0)), item("a", 5, box(0, 0))]);
    expect(placed.get("a")).toBe(0);
    expect(placed.get("b")).toBe(-1);
  });
});
