import { test as base, expect } from "@playwright/test";

/**
 * `test` с диагностикой: на упавшем тесте печатаем в stdout ошибки консоли и
 * страницы, состояние карты и настройки — в CI отчёт Playwright лежит в
 * артефакте, а лог джобы виден сразу. Карта в CI рисуется на SwiftShader без
 * GPU, и «почему камера не наклонилась» из одного скриншота не понять.
 */

interface MapDiag {
  pitch: number;
  zoom: number;
  terrain: boolean;
  projection: string | null;
  styleLoaded: boolean;
  loaded: boolean;
  moving: boolean;
  layers: number;
  windFrames: number | null;
  mapEl: boolean;
  fallback: string | null;
  prefs: string | null;
}

export const test = base.extend<{ diag: undefined }>({
  diag: [
    async ({ page }, use, testInfo) => {
      const log: string[] = [];
      page.on("console", (m) => {
        const text = m.text();
        if (m.type() === "error" || m.type() === "warning" || text.startsWith("[map.")) {
          log.push(`[console.${m.type()}] ${text.slice(0, 400)}`);
        }
      });
      page.on("pageerror", (e) => log.push(`[pageerror] ${e.message}`));
      // Исключение в кадре MapLibre глотается промисом кадра, а цикл отрисовки
      // молча умирает (камера замирает). Перехватываем _render, как только
      // карта появится в window.__mcMap, и печатаем стек в консоль.
      await page.addInitScript(() => {
        let current: unknown;
        Object.defineProperty(window, "__mcMap", {
          configurable: true,
          get: () => current,
          set: (map: Record<string, unknown> & { _render?: (t: number) => void }) => {
            current = map;
            const orig = map?._render;
            if (typeof orig !== "function") return;
            map._render = (t: number) => {
              try {
                orig.call(map, t);
              } catch (e) {
                console.error(`[frame] ${e instanceof Error ? (e.stack ?? e.message) : String(e)}`);
                throw e;
              }
            };
            // След камеры: кто двигает/останавливает её (в лог попадает только при падении)
            const traced = [
              "stop",
              "easeTo",
              "flyTo",
              "jumpTo",
              "setTerrain",
              "setProjection",
              "setStyle",
            ];
            for (const name of traced) {
              const fn = map[name];
              if (typeof fn !== "function") continue;
              map[name] = function (this: unknown, ...args: unknown[]) {
                const arg = args[0] === undefined ? "" : JSON.stringify(args[0])?.slice(0, 100);
                const where = (new Error().stack ?? "").split("\n").slice(2, 4).join(" | ");
                console.info(`[map.${name}] +${Math.round(performance.now())}ms ${arg} @ ${where}`);
                return (fn as (...a: unknown[]) => unknown).apply(this, args);
              };
            }
          },
        });
        // Дошёл ли клик до чекбокса/кнопки и когда
        document.addEventListener(
          "change",
          (e) => {
            const el = e.target as HTMLElement | null;
            console.info(
              `[map.dom.change] +${Math.round(performance.now())}ms ${el?.outerHTML.slice(0, 90)}`,
            );
          },
          true,
        );
      });
      await use(undefined);
      if (testInfo.status === testInfo.expectedStatus) return;
      const state = await page
        .evaluate((): MapDiag | null => {
          const w = window as unknown as {
            __mcMap?: import("maplibre-gl").Map;
            __mcWind?: { frames: number };
          };
          const map = w.__mcMap;
          if (!map) return null;
          return {
            pitch: map.getPitch(),
            zoom: map.getZoom(),
            terrain: !!map.getTerrain(),
            projection: String(map.getProjection()?.type ?? ""),
            styleLoaded: !!map.isStyleLoaded(),
            loaded: !!map.loaded(),
            moving: !!map.isMoving(),
            layers: map.getStyle()?.layers.length ?? -1,
            windFrames: w.__mcWind?.frames ?? null,
            mapEl: !!document.querySelector(".maplibregl-map canvas"),
            fallback:
              document.querySelector(".map-fallback, .ctrl-error")?.textContent?.slice(0, 200) ??
              null,
            prefs: localStorage.getItem("mc-map-prefs"),
          };
        })
        .catch((e: unknown) => String(e));
      const tail = log.filter((l) => !/ERR_TUNNEL|AJAXError|Failed to load resource/.test(l));
      console.log(
        `--- diag: ${testInfo.title}\nmap: ${JSON.stringify(state)}\n${tail.slice(-25).join("\n")}\n---`,
      );
    },
    { auto: true },
  ],
});

export { expect };
