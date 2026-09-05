import type { FeatureCollection } from "geojson";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { type GeoJSONSource, Marker, type Map as MLMap, Popup } from "maplibre-gl";
// Воркер MapLibre 6 ищется как ./maplibre-gl-worker.mjs рядом с чанком — в сборке
// Vite такого файла нет. Собираем воркер сами и говорим MapLibre его адрес; без
// воркера не грузятся ни тайлы, ни GeoJSON-слои (коридор, стрелки) — карта чёрная.
import maplibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import { useCallback, useEffect, useRef, useState } from "react";
import type { Snapshot, VesselStatus, WindField } from "../api";
import { fmtRelative } from "../format";
import { Interpolator, type Pose } from "./animate";
import { type LonLat, splitTrack } from "./geo";
import { windArrow } from "./icons";
import {
  nodeMarkerElement,
  renderNodeMarker,
  renderShipmentMarker,
  renderVesselMarker,
  shipmentMarkerElement,
  vesselMarkerElement,
} from "./markers";
import {
  BASEMAPS,
  type BasemapId,
  BOOT_STYLE,
  CORRIDOR_BOUNDS,
  DEM_SOURCE,
  isDarkBasemap,
  resolveStyle,
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
  terrain: boolean; // светотень рельефа (hillshade)
  terrain3d: boolean; // объёмный рельеф + наклон камеры
  sheetHeight: number; // видимая высота мобильной шторки, px (0 на десктопе)
  selectedRef: string | null;
  followRef: string | null; // груз, за которым едет камера
  focus: Focus | null;
  onSelectShipment: (ref: string | null) => void;
  onSelectNode: (code: string) => void;
  onStyleResolved: (fallback: boolean) => void;
  onFollowBroken: () => void; // пользователь сам подвинул карту — слежение снимаем
}

// Сила ветра → одна синяя шкала (тёмная подложка: слабый = темнее, сильный = светлее)
const WIND_BUCKETS = [4, 8, 12, 16, 20];
const WIND_COLORS = ["#1c5cab", "#2a78d6", "#3987e5", "#6da7ec", "#9ec5f4", "#cde2fb"];
const TRACK_COLOR = "#2fd39a";
const CORRIDOR_COLOR = "#8f86e6"; // лента коридора: не спорит ни с ветром, ни с грузами, ни со статусами
const FIRST_OVERLAY_LAYER = "corridor-glow"; // рельеф вставляется под него
const CORRIDOR_LAYERS = ["corridor-glow", "corridor-band", "routes-rail", "routes-sea"];

maplibregl.setWorkerUrl(maplibreWorkerUrl);

const SIDEBAR_PADDING = { top: 90, bottom: 40, left: 40, right: 420 };
const MOBILE_MAX_WIDTH = 900;
const FOLLOW_ZOOM = 6;
const PITCH_3D = 55; // наклон камеры при включении объёмного рельефа
const MAX_PITCH = 75;
const TERRAIN_EXAGGERATION = 1.6; // горы Кавказа и Тянь-Шаня читаются с зума 5
const FOLLOW_SETTLE_MS = 900; // пока камера подлетает к грузу, покадровое центрирование не мешает

/** Отступы для fitBounds/flyTo: справа сайдбар на десктопе, снизу шторка на мобильном. */
function viewportPadding(sheetPx: number) {
  if (window.innerWidth <= MOBILE_MAX_WIDTH) {
    const bottom = Math.min(sheetPx, window.innerHeight * 0.5) + 16;
    return { top: 170, bottom, left: 16, right: 16 };
  }
  return SIDEBAR_PADDING;
}

/** Время «доезда» до новой позиции: интервал обновления, в replay — короткое. */
function tweenDuration(snapshot: Snapshot): number {
  if (snapshot.replay) return 400; // шаг воспроизведения на шкале времени
  return Math.min(Math.max(snapshot.live.refresh_s * 1000, 2000), 10000);
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

  for (const id of ["routes", "wind", "track-rest", "track-done"]) {
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
      "line-layer-opacity": 0.22, // на весь слой: стыки сегментов не «двоятся» (MapLibre 6)
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
      "line-layer-opacity": 0.45,
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
}

function applyHillshade(map: MLMap, on: boolean, dark: boolean): void {
  if (!map.getLayer(FIRST_OVERLAY_LAYER)) return;
  if (!on) {
    if (map.getLayer("hillshade")) map.removeLayer("hillshade");
    if (map.getSource("dem") && !map.getTerrain()) map.removeSource("dem");
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
  terrain3d,
  sheetHeight,
  selectedRef,
  followRef,
  focus,
  onSelectShipment,
  onSelectNode,
  onStyleResolved,
  onFollowBroken,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MLMap | null>(null);
  const nodeMarkers = useRef(new Map<string, Marker>());
  const shipMarkers = useRef(new Map<string, Marker>());
  const vesselMarkers = useRef(new Map<string, Marker>());
  const popupRef = useRef<Popup | null>(null);
  const flownRef = useRef<string | null>(null);
  const styleRequest = useRef(0);
  // 0 = подложка ещё не загружена; растёт на каждый style.load — эффекты
  // переприменяют источники/слои после смены подложки
  const [styleVersion, setStyleVersion] = useState(0);

  // движение между снимками
  const interp = useRef(new Interpolator());
  const rafRef = useRef<number | null>(null);
  const followState = useRef<{ ref: string | null; settleUntil: number }>({
    ref: null,
    settleUntil: 0,
  });

  // колбэки в ref, чтобы обработчики карты не пересоздавались
  const callbacks = useRef({ onSelectShipment, onSelectNode, onStyleResolved, onFollowBroken });
  callbacks.current = { onSelectShipment, onSelectNode, onStyleResolved, onFollowBroken };
  const snapshotRef = useRef(snapshot);
  snapshotRef.current = snapshot;
  const sheetRef = useRef(sheetHeight);
  sheetRef.current = sheetHeight;
  const terrain3dRef = useRef(terrain3d);
  terrain3dRef.current = terrain3d;

  /** Кадр анимации: двигаем маркеры к целям, при слежении держим груз в центре. */
  const tick = useCallback(() => {
    const map = mapRef.current;
    rafRef.current = null;
    if (!map) return;
    const now = performance.now();
    for (const [ref, marker] of shipMarkers.current) {
      const pose = interp.current.pose(`s:${ref}`, now);
      if (pose) marker.setLngLat([pose.lon, pose.lat]);
    }
    for (const [name, marker] of vesselMarkers.current) {
      const pose = interp.current.pose(`v:${name}`, now);
      if (!pose) continue;
      marker.setLngLat([pose.lon, pose.lat]);
      const icon = marker.getElement().querySelector(".vessel-marker__icon") as HTMLElement | null;
      if (icon) icon.style.transform = `rotate(${pose.heading ?? 0}deg)`;
    }
    const follow = followState.current;
    if (follow.ref && now > follow.settleUntil) {
      const pose = interp.current.pose(`s:${follow.ref}`, now);
      const c = map.getCenter();
      if (pose && (Math.abs(c.lng - pose.lon) > 1e-7 || Math.abs(c.lat - pose.lat) > 1e-7)) {
        map.jumpTo({ center: [pose.lon, pose.lat] });
      }
    }
    if (interp.current.active(now) || follow.ref) {
      rafRef.current = requestAnimationFrame(tick);
    }
  }, []);
  const ensureLoop = useCallback(() => {
    if (rafRef.current == null) rafRef.current = requestAnimationFrame(tick);
  }, [tick]);

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
      maxPitch: MAX_PITCH,
      attributionControl: { compact: true },
    });
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "bottom-left");
    map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");
    mapRef.current = map;
    (window as unknown as { __mcMap?: MLMap }).__mcMap = map; // отладка из консоли

    const updateZoomBand = () => {
      const z = map.getZoom();
      containerRef.current?.setAttribute("data-zoom", z < 4.5 ? "far" : z < 6 ? "mid" : "near");
    };
    map.on("zoom", updateZoomBand);
    updateZoomBand();

    // клик по пустой карте снимает выбор; жест пользователя снимает слежение.
    // Снимаем синхронно: покадровый jumpTo вызывает map.stop(), который сбрасывает
    // обработчики жестов — ждать React-состояния нельзя, иначе drag превращается в click.
    map.on("click", () => callbacks.current.onSelectShipment(null));
    const breakFollow = (ev?: { originalEvent?: unknown }) => {
      if (ev && "originalEvent" in ev && !ev.originalEvent) return; // наша же анимация
      if (!followState.current.ref) return;
      followState.current = { ref: null, settleUntil: 0 };
      callbacks.current.onFollowBroken();
    };
    map.on("dragstart", breakFollow);
    map.on("wheel", breakFollow);
    map.on("dblclick", breakFollow);
    map.on("zoomstart", breakFollow);
    map.on("rotatestart", breakFollow);
    map.on("pitchstart", breakFollow);

    // style.load, а не load: load ждёт тайлы подложки, а они могут не грузиться
    // (офлайн, прокси) — оверлеи должны появляться независимо от подложки.
    // Срабатывает на каждую смену подложки: слои пересоздаются заново.
    map.on("style.load", () => {
      setupLayers(map);
      setStyleVersion((v) => v + 1);
    });

    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      map.remove();
      mapRef.current = null;
      nodeMarkers.current.clear();
      shipMarkers.current.clear();
      vesselMarkers.current.clear();
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
      if (map.getTerrain()) map.setTerrain(null); // на время смены стиля: иначе MapLibre падает в кадре без проекции
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
    // небо и туман видны при наклоне камеры (3D) и на глобусе
    const dark = isDarkBasemap(basemap);
    map.setSky({
      "sky-color": dark ? "#0a1220" : "#b9d1ee",
      "horizon-color": dark ? "#1b2842" : "#e4ecf6",
      "fog-color": dark ? "#0f1216" : "#eef0ec",
      "fog-ground-blend": 0.55,
      "horizon-fog-blend": 0.8,
      "sky-horizon-blend": 0.6,
      "atmosphere-blend": globe ? ["interpolate", ["linear"], ["zoom"], 0, 1, 4, 0.7, 7, 0] : 0,
    });
  }, [globe, basemap, styleVersion]);

  // --- рельеф: светотень поверх подложки под оверлеями; объём — terrain на том же DEM
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleVersion) return;
    if (!terrain3d && map.getTerrain()) map.setTerrain(null); // раньше hillshade: иначе источник dem не удалить
    applyHillshade(map, terrain || terrain3d, isDarkBasemap(basemap));
    if (terrain3d) {
      if (!map.getSource("dem")) map.addSource("dem", DEM_SOURCE);
      map.setTerrain({ source: "dem", exaggeration: TERRAIN_EXAGGERATION });
    }
  }, [terrain, terrain3d, basemap, styleVersion]);

  // наклон камеры — только по переключению пользователем, не при смене подложки
  const prev3d = useRef(terrain3d);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || prev3d.current === terrain3d) return;
    prev3d.current = terrain3d;
    if (terrain3d) {
      if (map.getPitch() < 20) map.easeTo({ pitch: PITCH_3D, duration: 1200 });
    } else {
      map.easeTo({ pitch: 0, bearing: 0, duration: 800 });
    }
  }, [terrain3d]);

  // --- данные снимка: маршрут, узлы, паромы, грузы ---------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleVersion || !snapshot || !map.getSource("routes")) return;
    const now = performance.now();
    const duration = tweenDuration(snapshot);

    (map.getSource("routes") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features: snapshot.segments.map((seg) => ({
        type: "Feature",
        properties: { mode: seg.mode },
        geometry: { type: "LineString", coordinates: seg.coordinates },
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

    // паромы с живой позицией — HTML-маркеры, чтобы ехать плавно вместе с грузами
    const seenVessels = new Set<string>();
    for (const v of snapshot.vessels) {
      if (!v.has_recent_data || v.lat == null || v.lon == null) continue;
      seenVessels.add(v.name);
      const pose: Pose = { lon: v.lon, lat: v.lat, heading: v.cog };
      let marker = vesselMarkers.current.get(v.name);
      if (!marker) {
        const el = vesselMarkerElement();
        el.addEventListener("click", (ev) => {
          ev.stopPropagation();
          const snap = snapshotRef.current;
          const vessel = snap?.vessels.find((x) => x.name === v.name);
          const m = vesselMarkers.current.get(v.name);
          if (!snap || !vessel || !m) return;
          popupRef.current?.remove();
          popupRef.current = new Popup({ closeButton: false, offset: 14 })
            .setLngLat(m.getLngLat())
            .setHTML(vesselPopupHtml(vessel, new Date(snap.generated_at)))
            .addTo(map);
        });
        marker = new Marker({ element: el, anchor: "center" }).setLngLat([v.lon, v.lat]).addTo(map);
        vesselMarkers.current.set(v.name, marker);
        interp.current.snap(`v:${v.name}`, pose, now);
      } else {
        interp.current.setTarget(`v:${v.name}`, pose, now, duration);
      }
      renderVesselMarker(
        marker.getElement() as HTMLDivElement,
        v,
        interp.current.pose(`v:${v.name}`, now)?.heading ?? v.cog,
      );
    }
    for (const [name, marker] of vesselMarkers.current) {
      if (!seenVessels.has(name)) {
        marker.remove();
        vesselMarkers.current.delete(name);
        interp.current.remove(`v:${name}`);
      }
    }

    const seenShips = new Set<string>();
    const atNodeCount = new Map<string, number>(); // грузы в одном узле — веером вниз
    for (const s of snapshot.shipments) {
      seenShips.add(s.ref);
      const pose: Pose = { lon: s.position.lon, lat: s.position.lat, heading: s.position.heading };
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
        interp.current.snap(`s:${s.ref}`, pose, now);
      } else {
        interp.current.setTarget(`s:${s.ref}`, pose, now, duration);
      }
      if (s.position.source === "event") {
        const idx = atNodeCount.get(s.position.from_code) ?? 0;
        atNodeCount.set(s.position.from_code, idx + 1);
        marker.setOffset([-7, 20 + 16 * idx]); // под подписью узла, не поверх неё
      } else {
        marker.setOffset([-7, 0]);
      }
      renderShipmentMarker(
        marker.getElement() as HTMLDivElement,
        s,
        s.ref === selectedRef,
        s.ref === followRef,
      );
    }
    for (const [ref, marker] of shipMarkers.current) {
      if (!seenShips.has(ref)) {
        marker.remove();
        shipMarkers.current.delete(ref);
        interp.current.remove(`s:${ref}`);
      }
    }
    ensureLoop();
  }, [snapshot, styleVersion, selectedRef, followRef, ensureLoop]);

  // --- слежение за грузом ----------------------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    const prev = followState.current.ref;
    followState.current = {
      ref: followRef,
      settleUntil: followRef && followRef !== prev ? performance.now() + FOLLOW_SETTLE_MS : 0,
    };
    if (!map || !followRef || followRef === prev) return;
    const pose = interp.current.pose(`s:${followRef}`, performance.now());
    if (pose) {
      map.easeTo({
        center: [pose.lon, pose.lat],
        zoom: Math.max(map.getZoom(), FOLLOW_ZOOM),
        pitch: terrain3dRef.current ? PITCH_3D : map.getPitch(),
        padding: viewportPadding(sheetRef.current),
        duration: FOLLOW_SETTLE_MS - 100,
      });
    }
    ensureLoop();
  }, [followRef, ensureLoop]);

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
    if (flownRef.current !== shipment.ref && followRef !== shipment.ref) {
      flownRef.current = shipment.ref;
      map.flyTo({
        center: [shipment.position.lon, shipment.position.lat],
        zoom: Math.max(map.getZoom(), 5.5),
        pitch: terrain3dRef.current ? PITCH_3D : map.getPitch(),
        padding: viewportPadding(sheetRef.current),
        duration: 900,
      });
    }
  }, [snapshot, styleVersion, selectedRef, followRef]);

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
    for (const id of CORRIDOR_LAYERS) map.setLayoutProperty(id, "visibility", vis(layers.routes));
    containerRef.current?.classList.toggle("hide-shipments", !layers.shipments);
    containerRef.current?.classList.toggle("hide-vessels", !layers.vessels);
    if (!layers.vessels) popupRef.current?.remove();
  }, [layers, styleVersion]);

  // --- подлёт по запросу сайдбара -------------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !focus) return;
    map.flyTo({
      center: [focus.lon, focus.lat],
      zoom: focus.zoom ?? Math.max(map.getZoom(), 6),
      pitch: terrain3dRef.current ? PITCH_3D : map.getPitch(),
      padding: viewportPadding(sheetRef.current),
      duration: 900,
    });
  }, [focus]);

  return <div ref={containerRef} className="map" data-zoom="far" data-basemap="dark" />;
}
