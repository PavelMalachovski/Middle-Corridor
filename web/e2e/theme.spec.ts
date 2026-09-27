import { expect, test } from "./fixtures";
import { openLayers, openMap, pinPrefs } from "./helpers";

/**
 * Тема: по умолчанию — как в системе, явный выбор запоминается; тёмная и
 * светлая подложки меняются вместе с темой. Плюс клавиатурный путь: ссылка
 * «к списку», фокус на заголовок карточки и обратно на строку списка.
 */

test.describe("тема по системе", () => {
  test.use({ colorScheme: "light" });

  test("светлая система: светлая тема и светлая подложка без настроек", async ({ page }) => {
    await openMap(page);
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    await expect(page.locator(".map")).toHaveAttribute("data-basemap", "light");
    await expect(page.locator('meta[name="theme-color"]')).toHaveAttribute("content", "#e9edf2");
    // панель действительно светлая: токены применились
    const bg = await page.locator(".topbar").evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(bg).toMatch(/^rgba?\(255, 255, 255/);
  });
});

test("переключатель темы: подложка следует, выбор переживает перезагрузку", async ({ page }) => {
  await openMap(page);
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator(".map")).toHaveAttribute("data-basemap", "dark");

  await page.getByRole("button", { name: "Светлая тема" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await expect(page.locator(".map")).toHaveAttribute("data-basemap", "light");

  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light"); // явный выбор важнее системы
  await expect(page.locator(".map")).toHaveAttribute("data-basemap", "light");
  const ui = await page.evaluate(() => localStorage.getItem("mc-ui"));
  expect(ui).toContain('"theme":"light"');

  await page.getByRole("button", { name: "Тёмная тема" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator(".map")).toHaveAttribute("data-basemap", "dark");
});

test("спутник не меняется вместе с темой", async ({ page }) => {
  await pinPrefs(page, {
    basemap: "satellite",
    globe: true,
    terrain: false,
    terrain3d: false,
    windMode: "arrows",
  });
  await openMap(page);
  await page.getByRole("button", { name: "Светлая тема" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  // data-basemap — яркость подложки (тёмная/светлая), не её id: спутник остаётся «тёмным»
  await expect(page.locator(".map")).toHaveAttribute("data-basemap", "dark");
  await openLayers(page);
  await expect(page.getByRole("button", { name: "Спутник", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  const prefs = await page.evaluate(() => localStorage.getItem("mc-map-prefs"));
  expect(prefs).toContain('"basemap":"satellite"');
});

test("клавиатура: пропуск к списку, фокус в карточку и обратно", async ({ page }) => {
  await openMap(page);
  await page.keyboard.press("Tab");
  const skip = page.getByRole("button", { name: "К списку грузов" });
  await expect(skip).toBeFocused();
  await expect(skip).toBeInViewport(); // видна при фокусе, а не только для скринридера
  await page.keyboard.press("Enter");
  await expect(page.locator("#panel-main")).toBeFocused();

  const card = page.locator(".list .card").first();
  const ref = await card.getAttribute("data-ref");
  await card.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator(".detail__ref")).toBeFocused();
  await expect(page.locator(".detail__ref")).toHaveText(ref ?? "");

  await page.getByRole("button", { name: /все грузы/ }).press("Enter");
  await expect(page.locator(`.list .card[data-ref="${ref}"]`)).toBeFocused();
});
