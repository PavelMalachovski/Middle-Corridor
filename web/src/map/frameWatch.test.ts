import { describe, expect, it } from "vitest";
import { FrameWatch } from "./frameWatch";

/** Кадры с шагом frameMs на отрезке [from, from + durationMs]; момент сигнала или null. */
function run(watch: FrameWatch, frameMs: number, durationMs: number, from = 0): number | null {
  for (let t = from; t <= from + durationMs; t += frameMs) if (watch.tick(t)) return t;
  return null;
}

describe("FrameWatch", () => {
  it("60 fps — сигнала нет", () => {
    expect(run(new FrameWatch(), 16, 60_000)).toBeNull();
  });

  it("2 fps — сигнал за секунды, а не через сотню кадров", () => {
    const at = run(new FrameWatch(), 500, 60_000);
    expect(at).not.toBeNull();
    expect(at as number).toBeLessThanOrEqual(6_000);
  });

  it("на грани порога — сигнал по окну в 3 с", () => {
    const at = run(new FrameWatch(), 60, 60_000);
    expect(at).not.toBeNull();
    expect(at as number).toBeGreaterThanOrEqual(3_000);
    expect(at as number).toBeLessThan(5_000);
  });

  it("короткий провал на секунду не считается", () => {
    const w = new FrameWatch();
    let t = 0;
    for (; t < 5_000; t += 16) expect(w.tick(t)).toBe(false);
    for (; t < 6_000; t += 200) expect(w.tick(t)).toBe(false); // секунда по 5 fps
    for (; t < 20_000; t += 16) expect(w.tick(t)).toBe(false);
  });

  it("пауза вкладки — не медленный кадр", () => {
    const w = new FrameWatch();
    w.tick(0);
    w.tick(16);
    expect(w.tick(10_016)).toBe(false); // вернулись через 10 с
    expect(run(w, 16, 10_000, 10_032)).toBeNull();
  });

  it("сигнал ровно один раз, сброс замеров его не возвращает", () => {
    const w = new FrameWatch();
    let signals = 0;
    for (let t = 0; t < 30_000; t += 500) if (w.tick(t)) signals += 1;
    expect(signals).toBe(1);
    w.reset();
    expect(run(w, 500, 30_000, 30_000)).toBeNull();
  });

  it("среднее время кадра доступно для шага частиц", () => {
    const w = new FrameWatch();
    run(w, 40, 2_000);
    expect(w.frameMs).toBeGreaterThan(30);
    expect(w.frameMs).toBeLessThan(41);
  });
});
