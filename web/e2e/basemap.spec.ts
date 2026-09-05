import { expect, test } from "./fixtures";
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

// Рельеф под SwiftShader (CI): первый кадр с terrain — секунды компиляции шейдеров
// на главном потоке и ещё секунды растеризации, второй кадр анимации камеры
// приходит позже любого разумного таймаута. С prefers-reduced-motion MapLibre
// делает easeTo мгновенным (jumpTo) — проверяем проводку переключателя
// (terrain, наклон, компас, обратно), а не скорость программного рендера.
test.describe("3D", () => {
  test.use({ contextOptions: { reducedMotion: "reduce" } });

  test("3D: наклон камеры и terrain, обратно — плоская карта", async ({ page }) => {
    test.slow(); // даже мгновенная камера ждёт кадр с рельефом: секунды на SwiftShader
    await pinPrefs(page); // без частиц — см. ARROWS_PREFS
    // на программном рендере приложение прячет «3D»; тесту нужен сам переключатель
    await page.addInitScript(() => localStorage.setItem("mc-force-gpu", "1"));
    await openMap(page);
    await page.getByText("3D", { exact: true }).click();
    await expect.poll(async () => Math.round((await mapState(page)).pitch)).toBe(55);
    expect((await mapState(page)).terrain).toBe(true);
    await expect(page.locator(".maplibregl-ctrl-compass")).toBeVisible();
    await page.getByText("3D", { exact: true }).click();
    await expect.poll(async () => Math.round((await mapState(page)).pitch)).toBe(0);
    expect((await mapState(page)).terrain).toBe(false);
  });
});
