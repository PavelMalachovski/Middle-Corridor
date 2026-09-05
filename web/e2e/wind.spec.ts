import { expect, test } from "@playwright/test";
import { openMap } from "./helpers";

declare global {
  interface Window {
    __mcWind?: { frames: number; ready: boolean };
  }
}

const PREFS = {
  basemap: "dark",
  globe: true,
  terrain: false,
  terrain3d: false,
  windMode: "particles",
};

test("ветер частицами: слой рисует кадры, стрелки — по переключателю", async ({ page }) => {
  await page.addInitScript(
    (prefs) => localStorage.setItem("mc-map-prefs", JSON.stringify(prefs)),
    PREFS,
  );
  await openMap(page);
  // слой поднялся и анимируется
  await expect
    .poll(() => page.evaluate(() => window.__mcWind?.ready ?? false), { timeout: 20_000 })
    .toBe(true);
  const f0 = await page.evaluate(() => window.__mcWind?.frames ?? 0);
  await expect
    .poll(() => page.evaluate(() => window.__mcWind?.frames ?? 0), { timeout: 10_000 })
    .toBeGreaterThan(f0 + 5);
  const vis = () =>
    page.evaluate(() => {
      const map = (window as unknown as { __mcMap: import("maplibre-gl").Map }).__mcMap;
      return {
        particles: map.getLayoutProperty("wind-particles", "visibility"),
        arrows: map.getLayoutProperty("wind-far", "visibility"),
      };
    });
  expect(await vis()).toEqual({ particles: "visible", arrows: "none" });

  // переключение на стрелки (SwiftShader в CI сам может переключить раньше — оба пути ведут сюда)
  await page.getByRole("button", { name: "Стрелки", exact: true }).click();
  await expect.poll(vis).toEqual({ particles: "none", arrows: "visible" });
  expect(await page.evaluate(() => localStorage.getItem("mc-map-prefs"))).toContain(
    '"windMode":"arrows"',
  );

  // выключить ветер целиком — гаснут и стрелки
  await page.getByRole("button", { name: "Ветер", exact: true }).click();
  await expect.poll(vis).toEqual({ particles: "none", arrows: "none" });
});

test("подложка меняется — слой частиц пересоздаётся без ошибок", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.addInitScript(
    (prefs) => localStorage.setItem("mc-map-prefs", JSON.stringify(prefs)),
    PREFS,
  );
  await openMap(page);
  await expect
    .poll(() => page.evaluate(() => window.__mcWind?.ready ?? false), { timeout: 20_000 })
    .toBe(true);
  await page.getByRole("button", { name: "Светлая" }).click();
  await expect
    .poll(
      () =>
        page.evaluate(() => {
          const map = (window as unknown as { __mcMap: import("maplibre-gl").Map }).__mcMap;
          return !!map.getLayer("wind-particles") && !!map.getLayer("corridor-glow");
        }),
      { timeout: 30_000 },
    )
    .toBe(true);
  const f0 = await page.evaluate(() => window.__mcWind?.frames ?? 0);
  await expect
    .poll(() => page.evaluate(() => window.__mcWind?.frames ?? 0), { timeout: 10_000 })
    .toBeGreaterThan(f0);
  expect(errors).toEqual([]);
});
