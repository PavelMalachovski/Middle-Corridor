import { type CSSProperties, lazy, Suspense, useCallback, useEffect, useState } from "react";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Legend } from "./components/Legend";
import { MapControls } from "./components/MapControls";
import { hasWebGL2, MapFallback } from "./components/MapFallback";
import { Sidebar, type Tab } from "./components/Sidebar";
import { Timeline } from "./components/Timeline";
import { TopBar } from "./components/TopBar";
import { useLiveData } from "./live";
import type { Focus, LayerToggles } from "./map/MapView";

// Карта с MapLibre — отдельный чанк: первый экран (панель, топбар) не ждёт её.
const MapView = lazy(() => import("./map/MapView").then((m) => ({ default: m.MapView })));

import { BASEMAPS, type BasemapId, DEFAULT_BASEMAP } from "./map/style";
import { useReplay } from "./replay";

// Настройки карты живут в localStorage — только удобство, без них всё работает
const PREFS_KEY = "mc-map-prefs";
interface MapPrefs {
  basemap: BasemapId;
  globe: boolean;
  terrain: boolean;
  terrain3d: boolean;
}
function loadPrefs(): MapPrefs {
  const prefs: MapPrefs = {
    basemap: DEFAULT_BASEMAP,
    globe: true,
    terrain: false,
    terrain3d: false,
  };
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    if (raw) {
      const saved = JSON.parse(raw) as Partial<MapPrefs>;
      if (saved.basemap && saved.basemap in BASEMAPS) prefs.basemap = saved.basemap;
      if (typeof saved.globe === "boolean") prefs.globe = saved.globe;
      if (typeof saved.terrain === "boolean") prefs.terrain = saved.terrain;
      if (typeof saved.terrain3d === "boolean") prefs.terrain3d = saved.terrain3d;
    }
  } catch {
    /* приватный режим и т.п. */
  }
  return prefs;
}
function savePrefs(prefs: MapPrefs): void {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
  } catch {
    /* ignore */
  }
}

const WEBGL2 = hasWebGL2(); // один раз на загрузку: контекст не появится позже

export function App() {
  const replay = useReplay();
  const { snapshot, wind, windAvailable, error, fetchedAt, mode } = useLiveData(replay.replayAt);
  useEffect(() => replay.sync(snapshot, fetchedAt), [replay, snapshot, fetchedAt]);
  const [selectedRef, setSelectedRef] = useState<string | null>(null);
  const [followRef, setFollowRef] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("shipments");
  const [layers, setLayers] = useState<LayerToggles>({
    wind: true,
    vessels: true,
    shipments: true,
    routes: true,
  });
  const [focus, setFocus] = useState<Focus | null>(null);
  const [prefs, setPrefs] = useState<MapPrefs>(loadPrefs);
  const [styleFallback, setStyleFallback] = useState(false);
  const [sheetHeight, setSheetHeight] = useState(0); // видимая высота шторки на мобильном
  const updatePrefs = useCallback((patch: Partial<MapPrefs>) => {
    setPrefs((p) => {
      const next = { ...p, ...patch };
      savePrefs(next);
      return next;
    });
  }, []);

  const selectShipment = useCallback((ref: string | null) => {
    setSelectedRef(ref);
    if (ref) setTab("shipments");
    else setFollowRef(null);
  }, []);

  const toggleFollow = useCallback((ref: string) => {
    setFollowRef((current) => (current === ref ? null : ref));
  }, []);

  const focusNode = useCallback(
    (code: string) => {
      const node = snapshot?.nodes.find((n) => n.code === code);
      if (!node) return;
      setSelectedNode(code);
      setFocus({ lon: node.lon, lat: node.lat, zoom: 6.5, key: Date.now() });
    },
    [snapshot],
  );

  const selectNodeFromMap = useCallback((code: string) => {
    setSelectedNode(code);
    setTab("ports");
    setSelectedRef(null);
  }, []);

  const focusShipment = useCallback(
    (ref: string) => {
      const s = snapshot?.shipments.find((x) => x.ref === ref);
      if (!s) return;
      setSelectedRef(ref);
      setFocus({
        lon: s.position.lon,
        lat: s.position.lat,
        zoom: 6,
        key: Date.now(),
      });
    },
    [snapshot],
  );

  return (
    <div
      className={`app ${sheetHeight > window.innerHeight * 0.6 ? "app--sheet-full" : ""}`}
      style={{ "--sheet-h": `${sheetHeight}px` } as CSSProperties}
    >
      {WEBGL2 ? (
        <ErrorBoundary
          scope="карта"
          fallback={(err, reset) => (
            <MapFallback
              title="Карта не отрисовалась"
              detail={`Панель справа работает. Ошибка: ${err.message}`}
              onRetry={reset}
            />
          )}
        >
          <Suspense fallback={<div className="map map--loading" aria-busy="true" />}>
            <MapView
              snapshot={snapshot}
              wind={wind}
              layers={layers}
              basemap={prefs.basemap}
              globe={prefs.globe}
              terrain={prefs.terrain}
              terrain3d={prefs.terrain3d}
              sheetHeight={sheetHeight}
              selectedRef={selectedRef}
              followRef={followRef}
              focus={focus}
              onSelectShipment={selectShipment}
              onSelectNode={selectNodeFromMap}
              onStyleResolved={setStyleFallback}
              onFollowBroken={() => setFollowRef(null)}
            />
          </Suspense>
        </ErrorBoundary>
      ) : (
        <MapFallback
          title="Карта недоступна в этом браузере"
          detail="Нужен WebGL 2: обновите браузер или откройте ссылку в Chrome, Safari 15+ или Firefox. Список грузов, порты и новости работают и без карты."
        />
      )}
      <ErrorBoundary
        scope="управление"
        fallback={(_err, reset) => (
          <button type="button" className="ctrl-error" onClick={reset}>
            Панель управления упала · перезагрузить
          </button>
        )}
      >
        <TopBar
          snapshot={snapshot}
          error={error}
          fetchedAt={fetchedAt}
          mode={mode}
          layers={layers}
          windAvailable={windAvailable}
          onToggle={(key) => setLayers((l) => ({ ...l, [key]: !l[key] }))}
        />
        <div className="left-stack">
          <Legend />
          <MapControls
            basemap={prefs.basemap}
            globe={prefs.globe}
            terrain={prefs.terrain}
            terrain3d={prefs.terrain3d}
            fallback={styleFallback}
            onBasemap={(basemap) => updatePrefs({ basemap })}
            onGlobe={(globe) => updatePrefs({ globe })}
            onTerrain={(terrain) => updatePrefs({ terrain })}
            onTerrain3d={(terrain3d) => updatePrefs({ terrain3d })}
          />
        </div>
        <Timeline replay={replay} disabled={!snapshot} />
      </ErrorBoundary>
      <ErrorBoundary
        scope="панель"
        fallback={(err, reset) => (
          <aside className="sidebar sidebar--error" role="alert">
            <div className="map-fallback">
              <div className="map-fallback__title">Панель не открылась</div>
              <div className="map-fallback__detail">Карта работает. Ошибка: {err.message}</div>
              <button type="button" className="chip chip--on" onClick={reset}>
                Перезагрузить панель
              </button>
            </div>
          </aside>
        )}
      >
        <Sidebar
          snapshot={snapshot}
          error={error}
          tab={tab}
          onTab={setTab}
          selectedRef={selectedRef}
          followRef={followRef}
          selectedNode={selectedNode}
          onSelectShipment={selectShipment}
          onToggleFollow={toggleFollow}
          onFocusShipment={focusShipment}
          onFocusNode={focusNode}
          onSheetChange={setSheetHeight}
        />
      </ErrorBoundary>
    </div>
  );
}
