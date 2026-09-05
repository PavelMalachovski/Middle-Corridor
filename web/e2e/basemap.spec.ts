import { expect, test } from "@playwright/test";
import { mapState, openMap, pinPrefs } from "./helpers";

test("смена подложки пересоздаёт наши слои; настройки запоминаются", async ({ page }) => {
  await openMap(page);
  await page.getByRole("button", { name: "Светлая" }).click();
  await expect(page.locator(".map")).toHaveAttribute("data-basemap", "light");
  await expect
    .poll(async () => (await mapState(page)).layers.includes("corridor-glow"), { timeout: 30_000 })
    .toBe(true);
  await expect(page.locator(".ship-marker").first()).toBeAttached();
  const prefs = await page.evaluate(() => localStorage.getItem("mc-map-prefs"));
  expect(prefs).toContain('"basemap":"light"');
});

test("3D: наклон камеры и terrain, обратно — плоская карта", async ({ page }) => {
  await pinPrefs(page); // тест про рельеф и наклон, не про ветер (см. ARROWS_PREFS)
  await openMap(page);
  await page.getByText("3D", { exact: true }).click();
  await expect.poll(async () => Math.round((await mapState(page)).pitch)).toBe(55);
  expect((await mapState(page)).terrain).toBe(true);
  await expect(page.locator(".maplibregl-ctrl-compass")).toBeVisible();
  await page.getByText("3D", { exact: true }).click();
  await expect.poll(async () => Math.round((await mapState(page)).pitch)).toBe(0);
  expect((await mapState(page)).terrain).toBe(false);
});
