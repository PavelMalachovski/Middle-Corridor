import { expect, test } from "./fixtures";
import { mapState, openMap, status } from "./helpers";

const ARROWS = {
  basemap: "dark",
  globe: true,
  terrain: false,
  terrain3d: false,
  windMode: "arrows",
};

test("ссылка открывает тот же груз в том же месте и на тот же момент", async ({ page }) => {
  await page.addInitScript((p) => localStorage.setItem("mc-map-prefs", JSON.stringify(p)), ARROWS);
  // момент — относительно серверных часов: мок с MOCK_TIME_SCALE живёт в своём времени
  const snap = (await (await page.request.get("/api/v1/snapshot")).json()) as {
    server_time: string;
  };
  const at = new Date(Date.parse(snap.server_time) - 6 * 3_600_000);
  at.setUTCMinutes(0, 0, 0);
  const iso = at.toISOString().replace(/\.\d{3}Z$/, "Z");
  await openMap(page, `/?s=mc-26-0412&view=6/43.5/50.5&basemap=light&at=${iso}`);
  await expect(page.locator(".detail__ref")).toHaveText("MC-26-0412");
  await expect(page.locator(".map")).toHaveAttribute("data-basemap", "light");
  const st = await mapState(page);
  expect(Math.abs(st.zoom - 6)).toBeLessThan(0.05);
  expect(Math.abs(st.center.lat - 43.5)).toBeLessThan(0.01);
  const hh = String(at.getUTCHours()).padStart(2, "0");
  await expect(status(page)).toContainText(
    `replay · ${String(at.getUTCDate()).padStart(2, "0")}.${String(at.getUTCMonth() + 1).padStart(2, "0")}, ${hh}:00`,
  );
  await expect(page).toHaveTitle(/MC-26-0412/);
});

test("поиск и фильтры сужают список, адрес отражает груз и вид карты", async ({ page }) => {
  await page.addInitScript((p) => localStorage.setItem("mc-map-prefs", JSON.stringify(p)), ARROWS);
  await openMap(page);
  const total = await page.locator(".list .card").count();
  await page.fill(".search", "0412");
  await expect(page.locator(".list .card")).toHaveCount(1);
  await page.fill(".search", "");
  await page.getByRole("button", { name: "с задержкой", exact: true }).click();
  const cards = page.locator(".list .card");
  expect(await cards.count()).toBeLessThan(total);
  await expect(cards.first().locator(".pill--delayed")).toBeVisible();
  await page
    .getByRole("button", { name: /сбросить/ })
    .first()
    .click();
  await expect(page.locator(".list .card")).toHaveCount(total);

  await page.locator(".list .card").first().click();
  await expect.poll(() => page.evaluate(() => location.search)).toMatch(/s=MC-26-\d{4}/);
  await page.evaluate(() => {
    (window as unknown as { __mcMap: import("maplibre-gl").Map }).__mcMap.easeTo({
      center: [45, 42],
      zoom: 5,
      duration: 200,
    });
  });
  await expect.poll(() => page.evaluate(() => location.search)).toMatch(/view=5\/42\/45/);
});

test("«поделиться» без Web Share кладёт ссылку в буфер и показывает тост", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.addInitScript((p) => localStorage.setItem("mc-map-prefs", JSON.stringify(p)), ARROWS);
  await openMap(page, "/?s=MC-26-0412");
  await expect(page.locator(".detail__ref")).toHaveText("MC-26-0412");
  await page.getByRole("button", { name: /поделиться/ }).click();
  await expect(page.locator(".toast")).toContainText("Ссылка скопирована");
  const clip = await page.evaluate(() => navigator.clipboard.readText());
  expect(clip).toContain("s=MC-26-0412");
});
