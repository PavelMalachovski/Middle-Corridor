import { expect, test } from "@playwright/test";
import { openMap } from "./helpers";

/** Переключатель RU/EN в топбаре: подписи интерфейса, узлов и маркеров; выбор запоминается. */

test("EN переводит интерфейс, названия узлов и подписи маркеров", async ({ page }) => {
  await openMap(page);
  await expect(page.locator("[data-tab=shipments]")).toContainText("Грузы");
  await expect(page.locator(".node-marker", { hasText: "Баку" }).first()).toBeAttached();

  await page.getByRole("button", { name: "EN", exact: true }).click();

  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.locator("[data-tab=shipments]")).toContainText("Cargo");
  await expect(page.locator(".topbar__kpis .kpi").first()).toContainText(/\d+ in transit/);
  await expect(page.getByRole("button", { name: "Wind", exact: true })).toBeVisible();
  await expect(page.locator(".node-marker", { hasText: "Baku" }).first()).toBeAttached();
  await expect(page.locator(".node-marker", { hasText: "Баку" })).toHaveCount(0);
  // подпись груза собирается из кодов события — тоже по-английски
  await expect(page.locator(".ship-marker").first()).toHaveAttribute("title", /[A-Za-z]/);
  await expect(page.locator(".ship-marker").first()).not.toHaveAttribute("title", /[А-Яа-я]/);
  await expect(page.locator("[data-tab=ports]")).toContainText("Ports");
});

test("выбор языка переживает перезагрузку", async ({ page }) => {
  await openMap(page);
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await expect(page.locator("[data-tab=shipments]")).toContainText("Cargo");

  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.locator("[data-tab=shipments]")).toContainText("Cargo");
  await expect(page.getByRole("button", { name: "EN", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );

  await page.getByRole("button", { name: "RU", exact: true }).click();
  await expect(page.locator("[data-tab=shipments]")).toContainText("Грузы");
  await expect(page.locator("html")).toHaveAttribute("lang", "ru");
});
