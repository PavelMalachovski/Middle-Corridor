import type { StyleSpecification } from "maplibre-gl";

/**
 * Подложки карты. Каждый пресет — список кандидатов по убыванию красоты:
 * векторные стили без ключа (OpenFreeMap, VersaTiles), а последним — растровый
 * стиль, собранный из тайлов CARTO/Esri. Перед применением стиль-URL
 * проверяется fetch'ем: если хост недоступен (офлайн, прокси, снятый стиль),
 * берём следующего кандидата — карта никогда не остаётся пустой.
 *
 * Свой стиль (MapTiler, Stadia, самохост) — через VITE_MAP_STYLE при сборке.
 */

export type BasemapId = "dark" | "light" | "detailed" | "satellite" | "custom";

export interface BasemapPreset {
  id: BasemapId;
  label: string;
  hint: string;
  candidates: (string | StyleSpecification)[];
}

const OSM_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
const CARTO_ATTRIBUTION = `${OSM_ATTRIBUTION} &copy; <a href="https://carto.com/attributions">CARTO</a>`;

function cartoTiles(variant: string): string[] {
  return ["a", "b", "c"].map(
    (s) => `https://${s}.basemaps.cartocdn.com/${variant}/{z}/{x}/{y}@2x.png`,
  );
}

function rasterStyle(
  background: string,
  base: { tiles: string[]; attribution: string; opacity?: number },
  labels?: { tiles: string[]; opacity?: number },
): StyleSpecification {
  const style: StyleSpecification = {
    version: 8,
    sources: {
      base: { type: "raster", tiles: base.tiles, tileSize: 256, attribution: base.attribution },
    },
    layers: [
      { id: "background", type: "background", paint: { "background-color": background } },
      {
        id: "base",
        type: "raster",
        source: "base",
        paint: { "raster-opacity": base.opacity ?? 1 },
      },
    ],
  };
  if (labels) {
    style.sources.labels = { type: "raster", tiles: labels.tiles, tileSize: 256 };
    style.layers.push({
      id: "labels",
      type: "raster",
      source: "labels",
      paint: { "raster-opacity": labels.opacity ?? 0.8 },
    });
  }
  return style;
}

export const RASTER_DARK_STYLE = rasterStyle(
  "#101418",
  { tiles: cartoTiles("dark_nolabels"), attribution: CARTO_ATTRIBUTION, opacity: 0.9 },
  { tiles: cartoTiles("dark_only_labels"), opacity: 0.75 },
);

const RASTER_LIGHT_STYLE = rasterStyle(
  "#e9ecef",
  { tiles: cartoTiles("light_nolabels"), attribution: CARTO_ATTRIBUTION },
  { tiles: cartoTiles("light_only_labels"), opacity: 0.9 },
);

const RASTER_DETAILED_STYLE = rasterStyle("#dfe6e9", {
  tiles: cartoTiles("rastertiles/voyager"),
  attribution: CARTO_ATTRIBUTION,
});

const SATELLITE_STYLE = rasterStyle(
  "#0b0f14",
  {
    tiles: [
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    ],
    attribution: "Imagery &copy; Esri, Maxar, Earthstar Geographics",
  },
  { tiles: cartoTiles("dark_only_labels"), opacity: 0.85 },
);

const CUSTOM_STYLE = import.meta.env.VITE_MAP_STYLE as string | undefined;

export const BASEMAPS: Record<BasemapId, BasemapPreset> = {
  dark: {
    id: "dark",
    label: "Тёмная",
    hint: "векторная, без ключа",
    candidates: [
      "https://tiles.versatiles.org/assets/styles/eclipse/style.json",
      "https://tiles.openfreemap.org/styles/dark",
      RASTER_DARK_STYLE,
    ],
  },
  light: {
    id: "light",
    label: "Светлая",
    hint: "Positron",
    candidates: [
      "https://tiles.openfreemap.org/styles/positron",
      "https://tiles.versatiles.org/assets/styles/graybeard/style.json",
      RASTER_LIGHT_STYLE,
    ],
  },
  detailed: {
    id: "detailed",
    label: "Детальная",
    hint: "дороги, рельеф, названия",
    candidates: [
      "https://tiles.openfreemap.org/styles/liberty",
      "https://tiles.versatiles.org/assets/styles/colorful/style.json",
      RASTER_DETAILED_STYLE,
    ],
  },
  satellite: {
    id: "satellite",
    label: "Спутник",
    hint: "снимки Esri + подписи",
    candidates: [SATELLITE_STYLE],
  },
  custom: {
    id: "custom",
    label: "Свой стиль",
    hint: "VITE_MAP_STYLE",
    candidates: CUSTOM_STYLE ? [CUSTOM_STYLE, RASTER_DARK_STYLE] : [RASTER_DARK_STYLE],
  },
};

export const AVAILABLE_BASEMAPS: BasemapPreset[] = [
  ...(CUSTOM_STYLE ? [BASEMAPS.custom] : []),
  BASEMAPS.dark,
  BASEMAPS.light,
  BASEMAPS.detailed,
  BASEMAPS.satellite,
];

export const DEFAULT_BASEMAP: BasemapId = CUSTOM_STYLE ? "custom" : "dark";

/** Тёмные подложки — для них подписи/иконки оверлеев остаются светлыми. */
export function isDarkBasemap(id: BasemapId): boolean {
  return id === "dark" || id === "satellite" || id === "custom";
}

export interface ResolvedStyle {
  style: string | StyleSpecification;
  fallback: boolean; // true = векторные кандидаты недоступны, взяли растр
}

/** Первый доступный кандидат пресета; последний (растровый объект) не требует проверки. */
export async function resolveStyle(preset: BasemapPreset): Promise<ResolvedStyle> {
  let skippedVector = false; // хотя бы один векторный кандидат не ответил
  for (const candidate of preset.candidates) {
    if (typeof candidate !== "string") return { style: candidate, fallback: skippedVector };
    try {
      const response = await fetch(candidate, { mode: "cors" });
      if (response.ok) {
        await response.json(); // это точно style.json, а не HTML-заглушка
        return { style: candidate, fallback: false };
      }
    } catch {
      /* пробуем следующего */
    }
    skippedVector = true;
  }
  return { style: preset.candidates[preset.candidates.length - 1], fallback: skippedVector };
}

// Рельеф: тайлы высот AWS Terrain Tiles (terrarium, без ключа)
export const DEM_SOURCE = {
  type: "raster-dem" as const,
  tiles: ["https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"],
  encoding: "terrarium" as const,
  tileSize: 256,
  maxzoom: 14,
  attribution: "Terrain &copy; Mapzen, AWS Terrain Tiles",
};

/** Пустой стиль на старте: тёмный фон появляется мгновенно, пока грузится подложка. */
export const BOOT_STYLE: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: "background", type: "background", paint: { "background-color": "#101418" } }],
};

/** Весь коридор от Констанцы до Хоргоса; Китай — по зуму наружу. */
export const CORRIDOR_BOUNDS: [[number, number], [number, number]] = [
  [26.0, 36.5],
  [82.5, 48.5],
];
