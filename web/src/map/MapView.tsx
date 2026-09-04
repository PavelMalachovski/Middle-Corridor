import { useEffect, useRef, useState } from "react";
import maplibregl, { type GeoJSONSource, type Map as MLMap, Marker, Popup } from "maplibre-gl";
import type { FeatureCollection } from "geojson";
import type { NodeStatus, Shipment, Snapshot, VesselStatus, WindField } from "../api";
import { LEVEL_ICON, fmtRelative, fmtWind, levelOf } from "../format";
import { shipIcon, windArrow } from "./icons";
import { splitTrack, type LonLat } from "./geo";
import {
  BASEMAPS,
  BOOT_STYLE,
  CORRIDOR_BOUNDS,
  DEM_SOURCE,
  isDarkBasemap,
  resolveStyle,
  type BasemapId,
} from "./style";

export interface LayerToggles {
  wind: boolean;
  vessels: boolean;
  shipments: boolean;
  routes: boolean;
}

export interface Focus {
  lon: number;
  lat: number;
  zoom?: number;
  key: number; // меняется при каждом запросе — чтобы повторный клик тоже сработал
}

interface Props {
  snapshot: Snapshot | null;
  wind: WindField | null;
  layers: LayerToggles;
  basemap: BasemapId;
  globe: boolean;
  terrain: boolean;
  sheetHeight: number; // видимая высота мобильной шторки, px (0 на десктопе)
  selectedRef: string | null;
  focus: Focus | null;
  onSelectShipment: (ref: string | null) => void;
  onSelectNode: (code: string) => void;
  onStyleResolved: (fallback: boolean) => void;
}

// Сила ветра → одна синяя шкала (тёмная подложка: слабый = темнее, сильный = светлее)
const WIND_BUCKETS = [4, 8, 12, 16, 20];
const WIND_COLORS = ["#1c5cab", "#2a78d6", "#3987e5", "#6da7ec", "#9ec5f4", "#cde2fb"];
const VESSEL_COLOR = "#eb6834";
const TRACK_COLOR = "#2fd39a";
const CORRIDOR_COLOR = "#8f86e6"; // лента коридора: не спорит ни с ветром, ни с грузами, ни со статусами
const FIRST_OVERLAY_LAYER = "corridor-glow"; // рельеф вставляется под него
const CORRIDOR_LAYERS = ["corridor-glow", "corridor-band", "routes-rail", "routes-sea"];

const SIDEBAR_PADDING = { top: 90, bottom: 40, left: 40, right: 420 };
const MOBILE_MAX_WIDTH = 900;

/** Отступы для fitBounds/flyTo: справа сайдбар на десктопе, снизу шторка на мобильном. */
function viewportPadding(sheetPx: number) {
  if (window.innerWidth <= MOBILE_MAX_WIDTH) {
    const bottom = Math.min(sheetPx, window.innerHeight * 0.5) + 16;
    return { top: 170, bottom, left: 16, right: 16 };
  }
  return SIDEBAR_PADDING;
}

function emptyFC(): FeatureCollection {
  return { type: "FeatureCollection", features: [] };
}

function tintIcon(
  image: { width: number; height: number; data: Uint8ClampedArray },
  hex: string,
): { width: number; height: number; data: Uint8ClampedArray } {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  const data = new Uint8ClampedArray(image.data);
  for (let i = 0; i < data.length; i += 4) {
    if (data[i + 3] === 0) continue;
    data[i] = r;
    data[i + 1] = g;
    data[i + 2] = b;
  }
  return { width: image.width, height: image.height, data };
}

/** Наши источники и слои поверх любой подложки. Вызывается на каждый style.load. */
function setupLayers(map: MLMap): void {
  const arrow = windArrow(32);
  WIND_COLORS.forEach((color, i) => {
    if (!map.hasImage(`wind-${i}`)) map.addImage(`wind-${i}`, tintIcon(arrow, color));
  });
  if (!map.hasImage("ship")) map.addImage("ship", tintIcon(shipIcon(36), VESSEL_COLOR));

  for (const id of ["routes", "wind", "vessels", "track-rest", "track-done"]) {
    if (!map.getSource(id)) map.addSource(id, { type: "geojson", data: emptyFC() });
  }
  if (map.getLayer(FIRST_OVERLAY_LAYER)) return;

  // Коридор как светящаяся лента: широкое размытое свечение + плотная полоса,
  // поверх — сами нитки маршрута (рельсы сплошные, море пунктиром)
  map.addLayer({
    id: "corridor-glow",
    type: "line",
    source: "routes",
    layout: { "line-cap": "round", "line-join": "round" },
    paint: {
      "line-color": CORRIDOR_COLOR,
      "line-width": ["interpolate", ["linear"], ["zoom"], 2, 10, 5, 22, 9, 48],
      "line-blur": ["interpolate", ["linear"], ["zoom"], 2, 5, 9, 16],
      "line-opacity": 0.22,
    },
  });
  map.addLayer({
    id: "corridor-band",
    type: "line",
    source: "routes",
    layout: { "line-cap": "round", "line-join": "round" },
    paint: {
      "line-color": CORRIDOR_COLOR,
      "line-width": ["interpolate", ["linear"], ["zoom"], 2, 3, 5, 6, 9, 12],
      "line-blur": ["interpolate", ["linear"], ["zoom"], 2, 1.5, 9, 4],
      "line-opacity": 0.45,
    },
  });
  map.addLayer({
    id: "routes-rail",
    type: "line",
    source: "routes",
    filter: ["==", ["get", "mode"], "rail"],
    layout: { "line-cap": "round", "line-join": "round" },
    paint: { "line-color": "#e4e7ee", "line-width": 1.6, "line-opacity": 0.85 },
  });
  map.addLayer({
    id: "routes-sea",
    type: "line",
    source: "routes",
    filter: ["==", ["get", "mode"], "sea"],
    paint: {
      "line-color": "#cfe0f5",
      "line-width": 1.6,
      "line-opacity": 0.85,
      "line-dasharray": [2, 2],
    },
  });
  map.addLayer({
    id: "wind",
    type: "symbol",
    source: "wind",
    layout: {
      "icon-image": [
        "step",
        ["get", "speed"],
        "wind-0",
        WIND_BUCKETS[0],
        "wind-1",
        WIND_BUCKETS[1],
        "wind-2",
        WIND_BUCKETS[2],
        "wind-3",
        WIND_BUCKETS[3],
        "wind-4",
        WIND_BUCKETS[4],
        "wind-5",
      ],
      "icon-rotate": ["+", ["get", "dir"], 180], // dir = откуда, стрелка показывает куда
      "icon-rotation-alignment": "map",
      "icon-allow-overlap": true,
      "icon-ignore-placement": true,
      // zoom допустим только во внешнем interpolate; внутри — зависимость от силы ветра
      "icon-size": [
        "interpolate",
        ["linear"],
        ["zoom"],
        3,
        ["interpolate", ["linear"], ["get", "speed"], 0, 0.2, 25, 0.55],
        8,
        ["interpolate", ["linear"], ["get", "speed"], 0, 0.45, 25, 1.2],
      ],
    },
    paint: { "icon-opacity": 0.8 },
  });
  map.addLayer({
    id: "track-rest",
    type: "line",
    source: "track-rest",
    paint: {
      "line-color": TRACK_COLOR,
      "line-width": 2.5,
      "line-opacity": 0.7,
      "line-dasharray": [1.5, 1.5],
    },
  });
  map.addLayer({
    id: "track-done",
    type: "line",
    source: "track-done",
    paint: { "line-color": TRACK_COLOR, "line-width": 3 },
  });
  map.addLayer({
    id: "vessels",
    type: "symbol",
    source: "vessels",
    layout: {
      "icon-image": "ship",
      "icon-rotate": ["coalesce", ["get", "cog"], 0],
      "icon-rotation-alignment": "map",
      "icon-allow-overlap": true,
      "icon-size": ["interpolate", ["linear"], ["zoom"], 3, 0.45, 8, 0.9],
    },
  });
}

function applyHillshade(map: MLMap, on: boolean, dark: boolean): void {
  if (!map.getLayer(FIRST_OVERLAY_LAYER)) return;
  if (!on) {
    if (map.getLayer("hillshade")) map.removeLayer("hillshade");
    if (map.getSource("dem")) map.removeSource("dem");
    return;
  }
  if (!map.getSource("dem")) map.addSource("dem", DEM_SOURCE);
  if (!map.getLayer("hillshade")) {
    map.addLayer(
      {
        id: "hillshade",
        type: "hillshade",
        source: "dem",
        paint: {
          "hillshade-exaggeration": dark ? 0.45 : 0.3,
          "hillshade-shadow-color": dark ? "#000000" : "#4a4a45",
          "hillshade-highlight-color": dark ? "#7a8ea3" : "#ffffff",
          "hillshade-accent-color": dark ? "#0b1220" : "#8a8a80",
        },
      },
      FIRST_OVERLAY_LAYER,
    );
  }
}

/** Меняет наши классы, не трогая maplibregl-marker* — иначе маркер выпадает из абсолютного позиционирования. */
function setOwnClasses(el: HTMLElement, classes: string[]): void {
  for (const cls of Array.from(el.classList)) {
    if (!cls.startsWith("maplibregl-")) el.classList.remove(cls);
  }
  el.classList.add(...classes.filter(Boolean));
}

function nodeMarkerElement(): HTMLDivElement {
  const el = document.createElement("div");
  el.className = "node-marker";
  el.innerHTML =
    '<div class="node-marker__dot"><i></i></div>' +
    '<div class="node-marker__label"><b></b><span></span></div>';
  return el;
}

function renderNodeMarker(el: HTMLDivElement, node: NodeStatus): void {
  const level = levelOf(node);
  setOwnClasses(el, ["node-marker", `node-marker--${node.kind}`, `level-${level}`]);
  el.title = node.alert_message ?? node.name;
  const label = el.querySelector("b")!;
  const sub = el.querySelector("span")!;
  label.textContent = node.name;
  if (node.is_weather_tracked && node.wind_speed != null) {
    const icon = node.alert_level ? `${LEVEL_ICON[node.alert_level]} ` : "";
    sub.textContent = `${icon}${node.wind_speed.toFixed(0)} м/с`;
  } else {
    sub.textContent = "";
  }
}

function shipmentMarkerElement(): HTMLDivElement {
  const el = document.createElement("div");
  el.className = "ship-marker";
  el.innerHTML = '<div class="ship-marker__dot"></div><div class="ship-marker__label"></div>';
  return el;
}

function renderShipmentMarker(el: HTMLDivElement, s: Shipment, selected: boolean): void {
  setOwnClasses(el, [
    "ship-marker",
    `ship-marker--${s.state}`,
    `ship-marker--${s.position.source}`,
    selected ? "is-selected" : "",
    s.delay_hours > 0 ? "is-delayed" : "",
  ]);
  el.title = `${s.ref}: ${s.last_event}`;
  el.querySelector(".ship-marker__label")!.textContent = s.ref;
}

function vesselPopupHtml(v: VesselStatus, ref: Date): string {
  const age = v.ts ? fmtRelative(v.ts, ref) : "нет данных";
  const sog = v.sog != null ? `${v.sog.toFixed(1)} уз` : "—";
  return `<div class="popup"><b>${v.name}</b><div>${v.route ?? ""} · ${v.phase ?? ""}</div><div>${sog} · AIS ${age}</div></div>`;
}

export function MapView({
  snapshot,
  wind,
  layers,
  basemap,
  globe,
  terrain,
  sheetHeight,
  selectedRef,
  focus,
  onSelectShipment,
  onSelectNode,
  onStyleResolved,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MLMap | null>(null);
  const nodeMarkers = useRef(new Map<string, Marker>());
  const shipMarkers = useRef(new Map<string, Marker>());
  const popupRef = useRef<Popup | null>(null);
  const flownRef = useRef<string | null>(null);
  const styleRequest = useRef(0);
  // 0 = подложка ещё не загружена; растёт на каждый style.load — эффекты
  // переприменяют источники/слои после смены подложки
  const [styleVersion, setStyleVersion] = useState(0);

  // колбэки в ref, чтобы обработчики карты не пересоздавались
  const callbacks = useRef({ onSelectShipment, onSelectNode, onStyleResolved });
  callbacks.current = { onSelectShipment, onSelectNode, onStyleResolved };
  const snapshotRef = useRef(snapshot);
  snapshotRef.current = snapshot;
  const sheetRef = useRef(sheetHeight);
  sheetRef.current = sheetHeight;

  useEffect(() => {
    if (!containerRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: BOOT_STYLE,
      bounds: CORRIDOR_BOUNDS,
      // на старте шторка ещё не отчиталась о высоте — берём её положение по умолчанию
      fitBoundsOptions: { padding: viewportPadding(window.innerHeight * 0.45) },
      minZoom: 1.5,
      maxZoom: 12,
      attributionControl: { compact: true },
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-left");
    map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");
    mapRef.current = map;
    (window as unknown as { __mcMap?: MLMap }).__mcMap = map; // отладка из консоли

    const updateZoomBand = () => {
      const z = map.getZoom();
      containerRef.current?.setAttribute("data-zoom", z < 4.5 ? "far" : z < 6 ? "mid" : "near");
    };
    map.on("zoom", updateZoomBand);
    updateZoomBand();

    map.on("click", "vessels", (e) => {
      const feature = e.features?.[0];
      const snap = snapshotRef.current;
      if (!feature || !snap) return;
      const vessel = snap.vessels.find((v) => v.name === feature.properties?.name);
      if (!vessel) return;
      popupRef.current?.remove();
      popupRef.current = new Popup({ closeButton: false, offset: 12 })
        .setLngLat(e.lngLat)
        .setHTML(vesselPopupHtml(vessel, new Date(snap.generated_at)))
        .addTo(map);
    });
    map.on("mouseenter", "vessels", () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", "vessels", () => (map.getCanvas().style.cursor = ""));
    map.on("click", (e) => {
      // клик по пустой карте снимает выбор
      const hits = map.getLayer("vessels")
        ? map.queryRenderedFeatures(e.point, { layers: ["vessels"] })
        : [];
      if (!hits.length) callbacks.current.onSelectShipment(null);
    });

    // style.load, а не load: load ждёт тайлы подложки, а они могут не грузиться
    // (офлайн, прокси) — оверлеи должны появляться независимо от подложки.
    // Срабатывает на каждую смену подложки: слои пересоздаются заново.
    map.on("style.load", () => {
      setupLayers(map);
      setStyleVersion((v) => v + 1);
    });

    return () => {
      map.remove();
      mapRef.current = null;
      nodeMarkers.current.clear();
      shipMarkers.current.clear();
      setStyleVersion(0);
    };
  }, []);

  // --- подложка: подбираем доступный стиль и применяем ----------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const request = ++styleRequest.current;
    void resolveStyle(BASEMAPS[basemap]).then(({ style, fallback }) => {
      if (request !== styleRequest.current || !mapRef.current) return; // уже выбрали другую
      map.setStyle(style, { diff: false });
      callbacks.current.onStyleResolved(fallback);
    });
    containerRef.current?.setAttribute("data-basemap", isDarkBasemap(basemap) ? "dark" : "light");
  }, [basemap]);

  // --- глобус и атмосфера ---------------------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleVersion) return;
    map.setProjection({ type: globe ? "globe" : "mercator" });
    map.setSky({
      "atmosphere-blend": globe ? ["interpolate", ["linear"], ["zoom"], 0, 1, 4, 0.7, 7, 0] : 0,
    });
  }, [globe, styleVersion]);

  // --- рельеф (hillshade поверх подложки, под оверлеями) --------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleVersion) return;
    applyHillshade(map, terrain, isDarkBasemap(basemap));
  }, [terrain, basemap, styleVersion]);

  // --- данные снимка: маршрут, суда, узлы, грузы ---------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleVersion || !snapshot || !map.getSource("routes")) return;

    (map.getSource("routes") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features: snapshot.segments.map((seg) => ({
        type: "Feature",
        properties: { mode: seg.mode },
        geometry: { type: "LineString", coordinates: seg.coordinates },
      })),
    });

    (map.getSource("vessels") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features: snapshot.vessels
        .filter((v) => v.has_recent_data && v.lat != null && v.lon != null)
        .map((v) => ({
          type: "Feature",
          properties: { name: v.name, cog: v.cog ?? 0 },
          geometry: { type: "Point", coordinates: [v.lon!, v.lat!] },
        })),
    });

    const seenNodes = new Set<string>();
    for (const node of snapshot.nodes) {
      seenNodes.add(node.code);
      let marker = nodeMarkers.current.get(node.code);
      if (!marker) {
        const el = nodeMarkerElement();
        el.addEventListener("click", (ev) => {
          ev.stopPropagation();
          callbacks.current.onSelectNode(node.code);
        });
        // anchor left + сдвиг на половину точки: координата — в центре точки, подпись справа
        marker = new Marker({ element: el, anchor: "left", offset: [-6, 0] })
          .setLngLat([node.lon, node.lat])
          .addTo(map);
        nodeMarkers.current.set(node.code, marker);
      }
      renderNodeMarker(marker.getElement() as HTMLDivElement, node);
    }
    for (const [code, marker] of nodeMarkers.current) {
      if (!seenNodes.has(code)) {
        marker.remove();
        nodeMarkers.current.delete(code);
      }
    }

    const seenShips = new Set<string>();
    const atNodeCount = new Map<string, number>(); // грузы в одном узле — веером вниз
    for (const s of snapshot.shipments) {
      seenShips.add(s.ref);
      let marker = shipMarkers.current.get(s.ref);
      if (!marker) {
        const el = shipmentMarkerElement();
        el.addEventListener("click", (ev) => {
          ev.stopPropagation();
          callbacks.current.onSelectShipment(s.ref);
        });
        marker = new Marker({ element: el, anchor: "left", offset: [-7, 0] })
          .setLngLat([s.position.lon, s.position.lat])
          .addTo(map);
        shipMarkers.current.set(s.ref, marker);
      } else {
        marker.setLngLat([s.position.lon, s.position.lat]);
      }
      if (s.position.source === "event") {
        const idx = atNodeCount.get(s.position.from_code) ?? 0;
        atNodeCount.set(s.position.from_code, idx + 1);
        marker.setOffset([-7, 20 + 16 * idx]); // под подписью узла, не поверх неё
      } else {
        marker.setOffset([-7, 0]);
      }
      renderShipmentMarker(marker.getElement() as HTMLDivElement, s, s.ref === selectedRef);
    }
    for (const [ref, marker] of shipMarkers.current) {
      if (!seenShips.has(ref)) {
        marker.remove();
        shipMarkers.current.delete(ref);
      }
    }
  }, [snapshot, styleVersion, selectedRef]);

  // --- выбранный груз: трек и подлёт ---------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleVersion || !map.getSource("track-done")) return;
    const shipment = snapshot?.shipments.find((s) => s.ref === selectedRef) ?? null;
    const done = map.getSource("track-done") as GeoJSONSource;
    const rest = map.getSource("track-rest") as GeoJSONSource;
    if (!shipment) {
      done.setData(emptyFC());
      rest.setData(emptyFC());
      flownRef.current = null;
      return;
    }
    const parts = splitTrack(shipment.track as LonLat[], shipment.progress);
    const line = (coords: LonLat[]): FeatureCollection => ({
      type: "FeatureCollection",
      features:
        coords.length > 1
          ? [
              {
                type: "Feature",
                properties: {},
                geometry: { type: "LineString", coordinates: coords },
              },
            ]
          : [],
    });
    done.setData(line(parts.done));
    rest.setData(line(parts.rest));
    if (flownRef.current !== shipment.ref) {
      flownRef.current = shipment.ref;
      map.flyTo({
        center: [shipment.position.lon, shipment.position.lat],
        zoom: Math.max(map.getZoom(), 5.5),
        padding: viewportPadding(sheetRef.current),
        duration: 900,
      });
    }
  }, [snapshot, styleVersion, selectedRef]);

  // --- ветер -----------------------------------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleVersion || !map.getSource("wind")) return;
    (map.getSource("wind") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features: (wind?.points ?? []).map((p) => ({
        type: "Feature",
        properties: { speed: p.speed, gust: p.gust, dir: p.dir },
        geometry: { type: "Point", coordinates: [p.lon, p.lat] },
      })),
    });
  }, [wind, styleVersion]);

  // --- видимость слоёв ------------------------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleVersion || !map.getLayer("wind")) return;
    const vis = (on: boolean) => (on ? "visible" : "none");
    map.setLayoutProperty("wind", "visibility", vis(layers.wind));
    map.setLayoutProperty("vessels", "visibility", vis(layers.vessels));
    for (const id of CORRIDOR_LAYERS) map.setLayoutProperty(id, "visibility", vis(layers.routes));
    containerRef.current?.classList.toggle("hide-shipments", !layers.shipments);
    if (!layers.vessels) popupRef.current?.remove();
  }, [layers, styleVersion]);

  // --- подлёт по запросу сайдбара -------------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !focus) return;
    map.flyTo({
      center: [focus.lon, focus.lat],
      zoom: focus.zoom ?? Math.max(map.getZoom(), 6),
      padding: viewportPadding(sheetRef.current),
      duration: 900,
    });
  }, [focus]);

  return <div ref={containerRef} className="map" data-zoom="far" data-basemap="dark" />;
}

export { fmtWind };
