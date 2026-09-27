import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures";
import { openMap } from "./helpers";

/**
 * Автоматическая проверка доступности (axe-core, WCAG 2.1 A/AA). Роняем тест
 * на serious/critical; moderate/minor печатаем в лог — это бэклог, а не регресс.
 * Холст карты исключён: его содержимое axe не видит, подписи — HTML-маркеры.
 */
async function audit(page: Page, where: string): Promise<void> {
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .exclude(".maplibregl-canvas")
    .analyze();
  const blocking = result.violations.filter(
    (v) => v.impact === "serious" || v.impact === "critical",
  );
  for (const v of result.violations) {
    const targets = v.nodes
      .slice(0, 3)
      .map((n) => n.target.join(" "))
      .join(" | ");
    console.log(`[a11y ${where}] ${v.impact} ${v.id} ×${v.nodes.length}: ${targets}`);
  }
  expect(
    blocking.map((v) => `${v.id}: ${v.help} (${v.nodes.length})`),
    `${where}: нарушения доступности`,
  ).toEqual([]);
}

test("доступность: обзор, карточка груза, порты, новости", async ({ page }) => {
  await openMap(page);
  await audit(page, "обзор");
  await page.locator(".list .card").first().click();
  await expect(page.locator(".detail")).toBeVisible();
  await audit(page, "карточка");
  await page.getByRole("tab", { name: /Порты/ }).click();
  await expect(page.locator(".list .card").first()).toBeVisible();
  await audit(page, "порты");
  await page.getByRole("tab", { name: /Новости/ }).click();
  await expect(page.locator(".sidebar__body li").first()).toBeVisible();
  await audit(page, "новости");
});
