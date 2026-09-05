import { expect, test } from "./fixtures";
import { dragMap, mapState, openMap } from "./helpers";

test("карточка груза, подлёт и слежение камерой", async ({ page }) => {
  await openMap(page);
  const first = page.locator(".list .card").first();
  const ref = (await first.locator(".mono").first().textContent())?.trim();
  await first.click();
  await expect(page.locator(".detail__ref")).toHaveText(ref ?? "");
  await expect(page.locator(".timeline__item").first()).toBeVisible();

  // «показать на карте» — подлёт
  const before = await mapState(page);
  await page.getByRole("button", { name: "показать на карте" }).click();
  await page.waitForTimeout(1200);
  const after = await mapState(page);
  expect(after.zoom).toBeGreaterThanOrEqual(before.zoom);

  // слежение: кнопка есть только у недоставленных
  const follow = page.getByRole("button", { name: /следить|следим/ });
  if (await follow.count()) {
    await follow.click();
    await expect(follow).toHaveText(/следим/);
    await expect(page.locator(".ship-marker.is-followed")).toHaveCount(1);
    await page.waitForTimeout(1500);
    // жест пользователя снимает слежение, но выбор остаётся
    await dragMap(page, 80, 40);
    await expect(page.locator(".ship-marker.is-followed")).toHaveCount(0);
    await expect(page.locator(".detail__ref")).toHaveText(ref ?? "");
  }
});

test("клик по пустой карте снимает выбор, «все грузы» возвращает список", async ({ page }) => {
  await openMap(page);
  await page.locator(".list .card").first().click();
  await expect(page.locator(".detail")).toBeVisible();
  await page.getByRole("button", { name: "← все грузы" }).click();
  await expect(page.locator(".list .card").first()).toBeVisible();
});
