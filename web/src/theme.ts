/**
 * Тема интерфейса: тёмная или светлая. По умолчанию — как в системе
 * (prefers-color-scheme); явный выбор человека помнит localStorage["mc-ui"].
 * Тема красит панели и текст (CSS-токены в styles.css), карта следует своей
 * подложке — но подложку по умолчанию подбираем под тему.
 */
import type { BasemapId } from "./map/style";

export type Theme = "dark" | "light";

// Цвет строки браузера и PWA — фон темы (--bg в styles.css)
const THEME_COLOR: Record<Theme, string> = { dark: "#0f1216", light: "#e9edf2" };

export function systemTheme(): Theme {
  if (typeof matchMedia !== "function") return "dark";
  return matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

/** Явный выбор важнее системы. */
export function resolveTheme(saved: unknown, system: Theme): Theme {
  return saved === "light" || saved === "dark" ? saved : system;
}

/** Тёмная и светлая подложки меняются вместе с темой; детальная, спутник и свой стиль — нет. */
export function basemapForTheme(current: BasemapId, theme: Theme): BasemapId {
  if (theme === "light" && current === "dark") return "light";
  if (theme === "dark" && current === "light") return "dark";
  return current;
}

export function applyTheme(theme: Theme): void {
  if (typeof document === "undefined") return;
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", THEME_COLOR[theme]);
}

/** Тема до первого рендера — без вспышки тёмного фона у светлой темы. */
export function initialTheme(): Theme {
  let saved: unknown;
  try {
    saved = (JSON.parse(localStorage.getItem("mc-ui") ?? "{}") as { theme?: unknown }).theme;
  } catch {
    /* приватный режим */
  }
  return resolveTheme(saved, systemTheme());
}
