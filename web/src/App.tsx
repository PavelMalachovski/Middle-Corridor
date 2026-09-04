import { useCallback, useEffect, useState } from "react";
import { fetchSnapshot, fetchWind, type Snapshot, type WindField } from "./api";
import { MapView, type Focus, type LayerToggles } from "./map/MapView";
import { BASEMAPS, DEFAULT_BASEMAP, type BasemapId } from "./map/style";
import { TopBar } from "./components/TopBar";
import { Legend } from "./components/Legend";
import { MapControls } from "./components/MapControls";
import { Sidebar, type Tab } from "./components/Sidebar";

const SNAPSHOT_MS = 10_000;
const WIND_MS = 60_000;

// Настройки карты живут в localStorage — только удобство, без них всё работает
const PREFS_KEY = "mc-map-prefs";
interface MapPrefs {
  basemap: BasemapId;
  globe: boolean;
  terrain: boolean;
}
function loadPrefs(): MapPrefs {
  const prefs: MapPrefs = { basemap: DEFAULT_BASEMAP, globe: true, terrain: false };
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    if (raw) {
      const saved = JSON.parse(raw) as Partial<MapPrefs>;
      if (saved.basemap && saved.basemap in BASEMAPS) prefs.basemap = saved.basemap;
      if (typeof saved.globe === "boolean") prefs.globe = saved.globe;
      if (typeof saved.terrain === "boolean") prefs.terrain = saved.terrain;
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

export function App() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [wind, setWind] = useState<WindField | null>(null);
  const [windAvailable, setWindAvailable] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fetchedAt, setFetchedAt] = useState<Date | null>(null);
  const [selectedRef, setSelectedRef] = useState<string | null>(null);
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
  const [, setTick] = useState(0); // перерисовка «N с назад» раз в секунду

  const updatePrefs = useCallback((patch: Partial<MapPrefs>) => {
    setPrefs((p) => {
      const next = { ...p, ...patch };
      savePrefs(next);
      return next;
    });
  }, []);

  useEffect(() => {
    let alive = true;
    const loadSnapshot = async () => {
      try {
        const data = await fetchSnapshot();
        if (!alive) return;
        setSnapshot(data);
        setFetchedAt(new Date());
        setError(null);
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      }
    };
    const loadWind = async () => {
      try {
        const data = await fetchWind();
        if (!alive) return;
        setWind(data);
        setWindAvailable(data !== null);
      } catch {
        /* ветер — вспомогательный слой, ошибку не показываем */
      }
    };
    void loadSnapshot();
    void loadWind();
    const a = setInterval(() => {
      if (document.visibilityState === "visible") void loadSnapshot();
    }, SNAPSHOT_MS);
    const b = setInterval(() => {
      if (document.visibilityState === "visible") void loadWind();
    }, WIND_MS);
    const c = setInterval(() => setTick((t) => t + 1), 1000);
    return () => {
      alive = false;
      clearInterval(a);
      clearInterval(b);
      clearInterval(c);
    };
  }, []);

  const selectShipment = useCallback((ref: string | null) => {
    setSelectedRef(ref);
    if (ref) setTab("shipments");
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

  const selectNodeFromMap = useCallback(
    (code: string) => {
      setSelectedNode(code);
      setTab("ports");
      setSelectedRef(null);
    },
    [],
  );

  const focusShipment = useCallback(
    (ref: string) => {
      const s = snapshot?.shipments.find((x) => x.ref === ref);
      if (!s) return;
      setSelectedRef(ref);
      setFocus({ lon: s.position.lon, lat: s.position.lat, zoom: 6, key: Date.now() });
    },
    [snapshot],
  );

  return (
    <div className="app">
      <MapView
        snapshot={snapshot}
        wind={wind}
        layers={layers}
        basemap={prefs.basemap}
        globe={prefs.globe}
        terrain={prefs.terrain}
        selectedRef={selectedRef}
        focus={focus}
        onSelectShipment={selectShipment}
        onSelectNode={selectNodeFromMap}
        onStyleResolved={setStyleFallback}
      />
      <TopBar
        snapshot={snapshot}
        error={error}
        fetchedAt={fetchedAt}
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
          fallback={styleFallback}
          onBasemap={(basemap) => updatePrefs({ basemap })}
          onGlobe={(globe) => updatePrefs({ globe })}
          onTerrain={(terrain) => updatePrefs({ terrain })}
        />
      </div>
      <Sidebar
        snapshot={snapshot}
        tab={tab}
        onTab={setTab}
        selectedRef={selectedRef}
        selectedNode={selectedNode}
        onSelectShipment={selectShipment}
        onFocusShipment={focusShipment}
        onFocusNode={focusNode}
      />
    </div>
  );
}
