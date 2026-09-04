import type { StyleSpecification } from "maplibre-gl";

// Базовая подложка — растровые тайлы CARTO Dark Matter (без ключа, атрибуция
// обязательна). Векторный стиль можно подставить через VITE_MAP_STYLE
// (URL style.json, например OpenFreeMap) — тогда этот объект не используется.
export const RASTER_DARK_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    carto: {
      type: "raster",
      tiles: [
        "https://a.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}@2x.png",
        "https://b.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}@2x.png",
        "https://c.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}@2x.png",
      ],
      tileSize: 256,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
    },
    cartoLabels: {
      type: "raster",
      tiles: [
        "https://a.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}@2x.png",
        "https://b.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}@2x.png",
        "https://c.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}@2x.png",
      ],
      tileSize: 256,
    },
  },
  layers: [
    { id: "background", type: "background", paint: { "background-color": "#101418" } },
    { id: "carto", type: "raster", source: "carto", paint: { "raster-opacity": 0.9 } },
    {
      id: "carto-labels",
      type: "raster",
      source: "cartoLabels",
      paint: { "raster-opacity": 0.75 },
    },
  ],
};

export const MAP_STYLE: string | StyleSpecification =
  (import.meta.env.VITE_MAP_STYLE as string | undefined) || RASTER_DARK_STYLE;

/** Весь коридор от Констанцы до Хоргоса; Китай — по зуму наружу. */
export const CORRIDOR_BOUNDS: [[number, number], [number, number]] = [
  [26.0, 36.5],
  [82.5, 48.5],
];
