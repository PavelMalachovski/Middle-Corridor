import { expect, type Page } from "@playwright/test";

/** Ждём первый снимок и маркеры грузов — карта и панель живы. */
export async function openMap(page: Page, path = "/"): Promise<void> {
  await page.goto(path, { waitUntil: "domcontentloaded" });
  await expect(page.locator(".list .card").first()).toBeVisible();
  await expect(page.locator(".ship-marker").first()).toBeAttached();
}

/** Статус в топбаре: «обновлено N с назад · поток» / «replay · …» / «нет связи с API». */
export function status(page: Page) {
  return page.locator(".topbar__status");
}

export interface MapState {
  pitch: number;
  zoom: number;
  center: { lng: number; lat: number };
  terrain: boolean;
  layers: string[];
}

/** Состояние карты через отладочный window.__mcMap. */
export function mapState(page: Page): Promise<MapState> {
  return page.evaluate(() => {
    const map = (window as unknown as { __mcMap: import("maplibre-gl").Map }).__mcMap;
    return {
      pitch: map.getPitch(),
      zoom: map.getZoom(),
      center: map.getCenter(),
      terrain: !!map.getTerrain(),
      layers: map.getStyle().layers.map((l) => l.id),
    };
  });
}

export async function markerPositions(page: Page): Promise<Record<string, [number, number]>> {
  return page.evaluate(() => {
    const out: Record<string, [number, number]> = {};
    for (const el of document.querySelectorAll<HTMLElement>(".ship-marker, .vessel-marker")) {
      const r = el.getBoundingClientRect();
      out[el.title.slice(0, 24)] = [Math.round(r.x * 10) / 10, Math.round(r.y * 10) / 10];
    }
    return out;
  });
}

/** Перетаскивание по карте мышью — снимает слежение, но не выбор. */
export async function dragMap(page: Page, dx: number, dy: number): Promise<void> {
  const canvas = page.locator(".maplibregl-canvas");
  const box = await canvas.boundingBox();
  if (!box) throw new Error("canvas not found");
  const x = box.x + box.width * 0.55;
  const y = box.y + box.height * 0.5;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + dx, y + dy, { steps: 8 });
  await page.mouse.up();
}
