import { expect, test } from "@playwright/test";
import { openMap } from "./helpers";

/** Верх шторки в px от верха окна. */
const sheetTop = (page: import("@playwright/test").Page) =>
  page.locator(".sidebar").evaluate((el) => Math.round(el.getBoundingClientRect().top));

async function dragHandle(
  page: import("@playwright/test").Page,
  dy: number,
  steps: number,
  waitMs: number,
) {
  const box = await page.locator(".sheet-handle").boundingBox();
  if (!box) throw new Error("no handle");
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  for (let i = 1; i <= steps; i++) {
    await page.mouse.move(x, y + (dy * i) / steps);
    await page.waitForTimeout(waitMs);
  }
  await page.mouse.up();
  await page.waitForTimeout(450);
}

test("шторка: полэкрана по умолчанию, свайпы, флики, тап по ручке", async ({ page }) => {
  await openMap(page);
  const h = page.viewportSize()?.height ?? 0;
  const FULL = Math.round(h - h * 0.88);
  const HALF = Math.round(h - h * 0.45);
  const PEEK = h - 64;

  expect(await sheetTop(page)).toBe(HALF);
  await dragHandle(page, -250, 25, 40); // медленно вверх → ближайшее положение
  expect(await sheetTop(page)).toBe(FULL);
  await dragHandle(page, 120, 4, 16); // флик вниз → на одно положение
  expect(await sheetTop(page)).toBe(HALF);
  await dragHandle(page, 120, 4, 16);
  expect(await sheetTop(page)).toBe(PEEK);
  // тап по ручке: клик по координатам, locator.click() на мобильной эмуляции
  // сначала «доскролливает» до элемента и промахивается
  const handle = await page.locator(".sheet-handle").boundingBox();
  if (!handle) throw new Error("no handle");
  await page.mouse.click(handle.x + handle.width / 2, handle.y + handle.height / 2);
  await page.waitForTimeout(450);
  expect(await sheetTop(page)).toBe(HALF);

  // шкала времени прижата к шторке, а не под ней
  const timeline = await page.locator(".timeline").boundingBox();
  expect(timeline).not.toBeNull();
  expect((timeline?.y ?? 0) + (timeline?.height ?? 0)).toBeLessThanOrEqual(HALF + 1);
});
