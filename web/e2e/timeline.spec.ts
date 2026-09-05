import { expect, test } from "@playwright/test";
import { openMap, status } from "./helpers";

async function scrub(page: import("@playwright/test").Page, hours: number) {
  await page.locator(".timeline__range").evaluate((el, h) => {
    const input = el as HTMLInputElement;
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    setter?.call(input, String(h));
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }, hours);
}

test("шкала времени: скраб, воспроизведение, пробел, LIVE", async ({ page }) => {
  await openMap(page);
  await scrub(page, -30);
  await expect(status(page)).toContainText("replay");
  await expect(page.locator(".timeline--replay")).toBeVisible();
  await expect(page.locator(".timeline__offset")).toHaveText("−30 ч");

  const readout = page.locator(".timeline__time");
  const t0 = await readout.textContent();
  await page.locator(".timeline__play").click();
  await expect(page.locator(".timeline.is-playing")).toBeVisible();
  await page.waitForTimeout(2500);
  expect(await readout.textContent()).not.toBe(t0); // время пошло

  await page.getByRole("button", { name: "×3600" }).click();
  await page.locator(".maplibregl-canvas").click({ position: { x: 700, y: 300 } });
  await page.keyboard.press("Space");
  await expect(page.locator(".timeline.is-playing")).toHaveCount(0);

  await page.getByRole("button", { name: "LIVE" }).click();
  await expect(page.locator(".timeline--live")).toBeVisible();
  await expect(status(page)).toContainText(/поток|поллинг/);
});

test("за краем окна запрос не уходит: значение прижимается", async ({ page }) => {
  await openMap(page);
  await scrub(page, -72);
  await expect(status(page)).toContainText("replay");
  await expect(status(page)).not.toContainText("нет связи");
});
