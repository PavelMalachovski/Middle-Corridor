import { expect, type Page, test } from "@playwright/test";
import { openMap } from "./helpers";

/** Верх шторки в px от верха окна. */
const sheetTop = (page: Page) =>
  page.locator(".sidebar").evaluate((el) => Math.round(el.getBoundingClientRect().top));

async function handleCenter(page: Page) {
  const box = await page.locator(".sheet-handle").boundingBox();
  if (!box) throw new Error("no handle");
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

/** Медленное перетаскивание: скорость заведомо ниже порога флика. */
async function dragSlow(page: Page, dy: number) {
  const { x, y } = await handleCenter(page);
  await page.mouse.move(x, y);
  await page.mouse.down();
  const steps = 25;
  for (let i = 1; i <= steps; i++) {
    await page.mouse.move(x, y + (dy * i) / steps);
    await page.waitForTimeout(40);
  }
  await page.mouse.up();
}

/**
 * Флик: одно движение без пауз. Скорость приложение меряет по реальному
 * времени между событиями, поэтому многошаговое движение с задержками на
 * медленном раннере CI перестаёт быть фликом.
 */
async function flick(page: Page, dy: number) {
  const { x, y } = await handleCenter(page);
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x, y + dy);
  await page.mouse.up();
}

/** Положение шторки после анимации (transition 0.25 с, на CI дольше). */
const expectSheet = (page: Page, top: number) =>
  expect.poll(() => sheetTop(page), { timeout: 5_000 }).toBe(top);

test("шторка: полэкрана по умолчанию, свайпы, флики, тап по ручке", async ({ page }) => {
  // тест про жесты, а не про ветер: частицы на SwiftShader грузят главный поток,
  // и скорость флика (по времени между событиями) перестаёт быть фликом
  await page.addInitScript(() =>
    localStorage.setItem(
      "mc-map-prefs",
      JSON.stringify({
        basemap: "dark",
        globe: true,
        terrain: false,
        terrain3d: false,
        windMode: "arrows",
      }),
    ),
  );
  await openMap(page);
  const h = page.viewportSize()?.height ?? 0;
  const FULL = Math.round(h - h * 0.88);
  const HALF = Math.round(h - h * 0.45);
  const PEEK = h - 64;

  await expectSheet(page, HALF);
  await dragSlow(page, -250); // медленно вверх → ближайшее положение
  await expectSheet(page, FULL);
  await flick(page, 160); // флик вниз → на одно положение
  await expectSheet(page, HALF);
  await flick(page, 160);
  await expectSheet(page, PEEK);
  await flick(page, -160); // флик вверх из peek
  await expectSheet(page, HALF);

  // тап по ручке: клик по координатам — locator.click() на мобильной эмуляции
  // сначала «доскролливает» до элемента и промахивается
  const half = await handleCenter(page);
  await page.mouse.click(half.x, half.y);
  await expectSheet(page, PEEK);
  const peek = await handleCenter(page); // ручка уехала вниз вместе со шторкой
  await page.mouse.click(peek.x, peek.y);
  await expectSheet(page, HALF);

  // шкала времени прижата к шторке, а не под ней
  const timeline = await page.locator(".timeline").boundingBox();
  expect(timeline).not.toBeNull();
  expect((timeline?.y ?? 0) + (timeline?.height ?? 0)).toBeLessThanOrEqual(HALF + 1);
});
