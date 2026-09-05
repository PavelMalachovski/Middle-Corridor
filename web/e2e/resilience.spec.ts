import { expect, test } from "./fixtures";
import { openMap, status } from "./helpers";

test("нет бэкенда: 404 от API — понятный статус, интерфейс не падает", async ({ page }) => {
  await page.route("**/api/v1/**", (route) => route.fulfill({ status: 404, body: "Not Found" }));
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(status(page)).toContainText("нет связи с API");
  await expect(status(page)).toContainText("HTTP 404");
  await expect(page.locator(".sidebar")).toBeVisible();
  await expect(page.locator(".timeline__play")).toBeDisabled();
});

test("источник упал: 503 с detail показывается в статусе", async ({ page }) => {
  await page.route("**/api/v1/snapshot**", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Источник данных недоступен" }),
    }),
  );
  await page.route("**/api/v1/stream**", (route) => route.abort());
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(status(page)).toContainText("HTTP 503");
});

test("без WebGL 2 — заглушка вместо карты, панель работает", async ({ page }) => {
  await page.addInitScript(() => {
    const orig = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (
      this: HTMLCanvasElement,
      type: string,
      ...rest: unknown[]
    ) {
      if (type === "webgl2") return null;
      return (orig as (this: HTMLCanvasElement, t: string, ...r: unknown[]) => unknown).call(
        this,
        type,
        ...rest,
      );
    } as typeof HTMLCanvasElement.prototype.getContext;
  });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".map--fallback")).toBeVisible();
  await expect(page.locator(".map-fallback__title")).toContainText("Карта недоступна");
  await expect(page.locator(".list .card").first()).toBeVisible();
});

test("вкладки портов и новостей догружаются лениво", async ({ page }) => {
  await openMap(page);
  await page.getByRole("button", { name: /Порты/ }).click();
  await expect(page.locator(".list .card").first()).toBeVisible();
  await page.getByRole("button", { name: /Новости/ }).click();
  await expect(page.locator(".sidebar__body li").first()).toBeVisible();
});
