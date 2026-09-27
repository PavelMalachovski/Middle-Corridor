import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { devices, type Page, type TestInfo } from "@playwright/test";
import { expect, test } from "./fixtures";
import { openMap } from "./helpers";

/**
 * Галерея экранов + инварианты раскладки. Скриншоты кладутся в web/screenshots/
 * и уходят артефактом CI на каждый прогон (не только на падении): ревьюер или
 * агент смотрит экраны, не запуская приложение. Пиксельного сравнения нет —
 * мок-данные движутся, тайлов в CI нет; вместо него — геометрические проверки
 * того, что раньше ловили только глазами (легенда под топбаром, полоска
 * маршрута поверх карты, топбар на пол-экрана телефона).
 */

const PREFS = JSON.stringify({
  basemap: "dark",
  globe: true,
  terrain: false,
  terrain3d: false,
  windMode: "arrows", // частицы на SwiftShader грузят поток и не детерминированы
});

async function shoot(page: Page, testInfo: TestInfo, name: string): Promise<void> {
  const dir = join(testInfo.project.testDir, "..", "screenshots");
  mkdirSync(dir, { recursive: true });
  const file = join(dir, `${name}.png`);
  await page.waitForTimeout(600); // дать маркерам доехать и шрифтам встать
  await page.screenshot({ path: file });
  await testInfo.attach(name, { path: file, contentType: "image/png" });
}

type Box = { x: number; y: number; width: number; height: number };

async function box(page: Page, selector: string): Promise<Box | null> {
  const el = page.locator(selector).first();
  if (!(await el.isVisible())) return null;
  return el.boundingBox();
}

function intersects(a: Box, b: Box): boolean {
  return (
    a.x < b.x + b.width - 1 &&
    b.x < a.x + a.width - 1 &&
    a.y < b.y + b.height - 1 &&
    b.y < a.y + a.height - 1
  );
}

/** Панели поверх карты не должны наезжать друг на друга. */
async function expectNoOverlap(page: Page, pairs: [string, string][]): Promise<void> {
  for (const [a, b] of pairs) {
    const [ba, bb] = [await box(page, a), await box(page, b)];
    if (!ba || !bb) continue;
    expect(intersects(ba, bb), `${a} наезжает на ${b}: ${JSON.stringify([ba, bb])}`).toBe(false);
  }
}

/** Ни страница, ни тело панели не прокручиваются вбок. */
async function expectNoHorizontalOverflow(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => {
    const out: string[] = [];
    if (document.documentElement.scrollWidth > window.innerWidth + 1) out.push("document");
    for (const el of document.querySelectorAll<HTMLElement>(".sidebar__body, .sidebar__body *")) {
      const style = getComputedStyle(el);
      if (style.overflowX === "auto" || style.overflowX === "scroll") continue; // прокрутка задумана
      if (el.classList.contains("sr-only")) continue; // подпись для скринридера: 1×1 px нарочно
      if (el.scrollWidth > el.clientWidth + 2 && el.clientWidth > 0)
        out.push(`${el.className || el.tagName} ${el.scrollWidth}>${el.clientWidth}`);
    }
    return out.slice(0, 5);
  });
  expect(overflow, "горизонтальное переполнение").toEqual([]);
}

const DESKTOP_PAIRS: [string, string][] = [
  [".topbar", ".legend"],
  [".topbar", ".sidebar"],
  [".left-stack", ".timeline"],
  [".timeline", ".sidebar"],
  [".legend", ".mapctl"],
];

test.describe("экраны: десктоп", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript((prefs) => localStorage.setItem("mc-map-prefs", prefs), PREFS);
  });

  for (const size of [
    { width: 1440, height: 860 },
    { width: 1280, height: 720 },
  ]) {
    test(`обзор ${size.width}×${size.height}: панели не наезжают`, async ({ page }, testInfo) => {
      await page.setViewportSize(size);
      await openMap(page);
      await expectNoOverlap(page, DESKTOP_PAIRS);
      await expectNoHorizontalOverflow(page);
      await shoot(page, testInfo, `overview-${size.width}`);
    });
  }

  test("карточка груза, порты, новости", async ({ page }, testInfo) => {
    await openMap(page);
    await page.locator(".list .card").first().click();
    await expect(page.locator(".detail")).toBeVisible();
    await expectNoHorizontalOverflow(page);
    await shoot(page, testInfo, "card");

    await page.getByRole("tab", { name: /Порты/ }).click();
    await expect(page.locator(".list .card").first()).toBeVisible();
    await page.locator(".list .card").first().click(); // выбранный порт: спарклайн прогноза
    await expectNoHorizontalOverflow(page);
    await shoot(page, testInfo, "ports");

    await page.getByRole("tab", { name: /Новости/ }).click();
    await expect(page.locator(".sidebar__body li").first()).toBeVisible();
    await expectNoHorizontalOverflow(page);
    await shoot(page, testInfo, "news");
  });

  test("английский, светлая подложка, replay", async ({ page }, testInfo) => {
    await openMap(page);
    await page.getByRole("button", { name: "EN", exact: true }).click();
    await expect(page.locator("[data-tab=shipments]")).toContainText("Cargo");
    await expectNoOverlap(page, DESKTOP_PAIRS);
    await shoot(page, testInfo, "en");

    await page.getByRole("button", { name: "Light", exact: true }).click();
    await expect(page.locator(".map")).toHaveAttribute("data-basemap", "light");
    await page.waitForTimeout(1500);
    await shoot(page, testInfo, "light");

    await page.locator(".timeline__range").evaluate((el) => {
      // React слушает input через свой сеттер value — как в timeline.spec.ts
      const input = el as HTMLInputElement;
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
      setter?.call(input, "-30");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await expect(page.locator(".timeline--replay")).toBeVisible();
    await shoot(page, testInfo, "replay");
  });

  test("API недоступен: прочерки вместо нулей", async ({ page }, testInfo) => {
    await page.route("**/api/v1/**", (route) => route.fulfill({ status: 503, body: "{}" }));
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.locator(".topbar__status")).toContainText("HTTP 503");
    await expect(page.locator(".topbar__kpis .kpi b").first()).toHaveText("—");
    await shoot(page, testInfo, "api-down");
  });
});

const { defaultBrowserType: _browser, ...pixel } = devices["Pixel 7"];

test.describe("экраны: телефон", () => {
  test.use(pixel);
  test.beforeEach(async ({ page }) => {
    await page.addInitScript((prefs) => localStorage.setItem("mc-map-prefs", prefs), PREFS);
  });

  test("топбар компактный, карте остаётся место", async ({ page }, testInfo) => {
    await openMap(page);
    const vh = page.viewportSize()?.height ?? 0;
    const top = await box(page, ".topbar");
    const timeline = await box(page, ".timeline");
    expect(top && top.height < vh * 0.22, `топбар ${top?.height}px из ${vh}`).toBe(true);
    // между топбаром и шкалой времени — видимая карта, а не щель
    const mapGap = (timeline?.y ?? 0) - ((top?.y ?? 0) + (top?.height ?? 0));
    expect(mapGap, `карте осталось ${mapGap}px`).toBeGreaterThan(vh * 0.2);
    await expectNoHorizontalOverflow(page);
    await shoot(page, testInfo, "mobile-half");
  });

  test("карточка груза и порты в шторке", async ({ page }, testInfo) => {
    await openMap(page);
    await page.locator(".list .card").first().click();
    await expect(page.locator(".detail")).toBeVisible();
    await expectNoHorizontalOverflow(page);
    await shoot(page, testInfo, "mobile-card");
    await page.getByRole("tab", { name: /Порты/ }).click();
    await expect(page.locator(".list .card").first()).toBeVisible();
    await shoot(page, testInfo, "mobile-ports");
  });
});
