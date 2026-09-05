import { expect, test } from "@playwright/test";
import { markerPositions, openMap, status } from "./helpers";

test("первый экран: снимок, поток, маркеры, легенда", async ({ page }, testInfo) => {
  await openMap(page);
  await expect(status(page)).toContainText(/поток|поллинг/);
  await expect(page.locator(".topbar__kpis .kpi").first()).toContainText(/\d+ в пути/);
  await expect(page.locator(".vessel-marker").first()).toBeAttached();
  await expect(page.locator(".legend")).toBeVisible();
  await expect(page.locator(".timeline--live")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("overview.png") });
  await testInfo.attach("overview", {
    path: testInfo.outputPath("overview.png"),
    contentType: "image/png",
  });
});

test("объекты движутся между снимками плавно, а не прыжком", async ({ page }) => {
  await openMap(page);
  await page.waitForTimeout(2500); // первый tween уже идёт
  const frames: string[] = [];
  for (let i = 0; i < 6; i++) {
    await page.waitForTimeout(500);
    frames.push(JSON.stringify(await markerPositions(page)));
  }
  // хотя бы один объект прошёл через 3+ разных положения за 3 секунды
  const positions = frames.map((f) => JSON.parse(f) as Record<string, [number, number]>);
  const distinct = Object.keys(positions[0]).map(
    (k) => new Set(positions.map((p) => p[k]?.join(","))).size,
  );
  expect(Math.max(...distinct)).toBeGreaterThanOrEqual(3);
});

test("переключатели слоёв прячут грузы и паромы", async ({ page }) => {
  await openMap(page);
  await page.getByRole("button", { name: "Грузы", exact: true }).click();
  await expect(page.locator(".map")).toHaveClass(/hide-shipments/);
  await page.getByRole("button", { name: "Паромы", exact: true }).click();
  await expect(page.locator(".map")).toHaveClass(/hide-vessels/);
});
