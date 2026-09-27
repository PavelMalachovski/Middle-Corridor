// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { applyTheme, basemapForTheme, initialTheme, resolveTheme } from "./theme";

afterEach(() => localStorage.clear());

describe("тема", () => {
  it("явный выбор важнее системы, мусор — нет", () => {
    expect(resolveTheme("light", "dark")).toBe("light");
    expect(resolveTheme("dark", "light")).toBe("dark");
    expect(resolveTheme(undefined, "light")).toBe("light");
    expect(resolveTheme("sepia", "dark")).toBe("dark");
  });

  it("тёмная и светлая подложки следуют теме, остальные — нет", () => {
    expect(basemapForTheme("dark", "light")).toBe("light");
    expect(basemapForTheme("light", "dark")).toBe("dark");
    expect(basemapForTheme("satellite", "light")).toBe("satellite");
    expect(basemapForTheme("detailed", "dark")).toBe("detailed");
  });

  it("сохранённая тема из mc-ui и атрибут на <html>", () => {
    localStorage.setItem("mc-ui", JSON.stringify({ theme: "light" }));
    expect(initialTheme()).toBe("light");
    const meta = document.createElement("meta");
    meta.name = "theme-color";
    document.head.append(meta);
    applyTheme("light");
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(meta.content).toBe("#e9edf2");
  });
});
