import { describe, expect, it } from "vitest";
import { Interpolator } from "./animate";

const A = { lon: 50, lat: 40, heading: 350 };
const B = { lon: 52, lat: 42, heading: 10 };

describe("Interpolator", () => {
  it("едет от старой точки к новой и приезжает ровно в цель", () => {
    const it_ = new Interpolator();
    it_.snap("s", A, 0);
    it_.setTarget("s", B, 0, 1000);
    expect(it_.pose("s", 0)).toEqual(A);
    const mid = it_.pose("s", 500);
    expect(mid).not.toBeNull();
    expect(mid!.lon).toBeGreaterThan(50);
    expect(mid!.lon).toBeLessThan(52);
    expect(it_.pose("s", 1000)).toEqual(B);
    expect(it_.pose("s", 5000)).toEqual(B);
  });

  it("ease-out: первая половина времени проходит больше половины пути", () => {
    const it_ = new Interpolator();
    it_.snap("s", A, 0);
    it_.setTarget("s", B, 0, 1000);
    expect(it_.pose("s", 500)!.lon).toBeGreaterThan(51);
  });

  it("курс поворачивает по короткой дуге через север", () => {
    const it_ = new Interpolator();
    it_.snap("s", A, 0);
    it_.setTarget("s", B, 0, 1000);
    const h = it_.pose("s", 500)!.heading!;
    // 350 → 10 через 0, а не через 180
    expect(h < 20 || h > 340).toBe(true);
    expect(it_.pose("s", 1000)!.heading).toBe(10);
  });

  it("новая цель посреди движения стартует из текущей точки без рывка", () => {
    const it_ = new Interpolator();
    it_.snap("s", A, 0);
    it_.setTarget("s", B, 0, 1000);
    const before = it_.pose("s", 400)!;
    it_.setTarget("s", { lon: 60, lat: 45, heading: 90 }, 400, 1000);
    const after = it_.pose("s", 400)!;
    expect(after.lon).toBeCloseTo(before.lon, 9);
    expect(after.lat).toBeCloseTo(before.lat, 9);
  });

  it("нулевая длительность и та же цель ставят объект сразу", () => {
    const it_ = new Interpolator();
    it_.setTarget("s", A, 0, 0);
    expect(it_.pose("s", 0)).toEqual(A);
    it_.setTarget("s", A, 10, 1000); // цель не изменилась — движения нет
    expect(it_.active(10)).toBe(false);
  });

  it("active/has/remove/ids", () => {
    const it_ = new Interpolator();
    expect(it_.has("s")).toBe(false);
    it_.snap("s", A, 0);
    it_.setTarget("s", B, 0, 1000);
    expect(it_.active(500)).toBe(true);
    expect(it_.active(1000)).toBe(false);
    expect([...it_.ids()]).toEqual(["s"]);
    it_.remove("s");
    expect(it_.has("s")).toBe(false);
    expect(it_.pose("s", 0)).toBeNull();
  });
});
