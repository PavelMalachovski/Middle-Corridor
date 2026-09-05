import { describe, expect, it } from "vitest";
import { HEADER_PX, maxOffset, offsetFor, snapSheet, visibleFor } from "./sheet";

const H = 800; // innerHeight

describe("геометрия шторки", () => {
  it("видимая высота: peek — только заголовок, half/full — доля экрана", () => {
    expect(visibleFor("peek", H)).toBe(HEADER_PX);
    expect(visibleFor("half", H)).toBe(360);
    expect(visibleFor("full", H)).toBe(704);
  });
  it("смещение растёт сверху вниз, максимум оставляет заголовок", () => {
    expect(offsetFor("full", H)).toBe(0);
    expect(offsetFor("half", H)).toBe(344);
    expect(offsetFor("peek", H)).toBe(640);
    expect(maxOffset(H)).toBe(640);
  });
});

describe("snapSheet", () => {
  it("медленное перетаскивание — к ближайшему положению", () => {
    expect(snapSheet("half", 300, 0, H)).toBe("half");
    expect(snapSheet("half", 100, 0, H)).toBe("full");
    expect(snapSheet("half", 500, 0, H)).toBe("peek");
    expect(snapSheet("full", 640, 0.1, H)).toBe("peek");
  });
  it("флик вниз опускает на одно положение, у нижнего края остаётся", () => {
    expect(snapSheet("full", 10, 1, H)).toBe("half");
    expect(snapSheet("half", 350, 1, H)).toBe("peek");
    expect(snapSheet("peek", 640, 1, H)).toBe("peek");
  });
  it("флик вверх поднимает на одно положение, у верхнего края остаётся", () => {
    expect(snapSheet("peek", 600, -1, H)).toBe("half");
    expect(snapSheet("half", 300, -1, H)).toBe("full");
    expect(snapSheet("full", 0, -1, H)).toBe("full");
  });
  it("порог флика: чуть медленнее — обычное перетаскивание", () => {
    expect(snapSheet("full", 600, 0.39, H)).toBe("peek"); // по расстоянию
    expect(snapSheet("full", 600, 0.41, H)).toBe("half"); // по флику — на одно положение
  });
});
