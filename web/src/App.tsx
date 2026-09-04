import { useCallback, useEffect, useState, type CSSProperties } from "react";
import { useLiveData } from "./live";
import { useReplay } from "./replay";
import { MapView, type Focus, type LayerToggles } from "./map/MapView";
import { BASEMAPS, DEFAULT_BASEMAP, type BasemapId } from "./map/style";
import { TopBar } from "./components/TopBar";
import { Legend } from "./components/Legend";
import { MapControls } from "./components/MapControls";
import { Sidebar, type Tab } from "./components/Sidebar";
import { Timeline } from "./components/Timeline";

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
    <div className="app" style={{ "--sheet-h": `${sheetHeight}px` } as CSSProperties}>
      <MapView
        snapshot={snapshot}
        wind={wind}
        layers={layers}
        basemap={prefs.basemap}
        globe={prefs.globe}
        terrain={prefs.terrain}
        sheetHeight={sheetHeight}
        selectedRef={selectedRef}
        followRef={followRef}
        focus={focus}
        onSelectShipment={selectShipment}
        onSelectNode={selectNodeFromMap}
        onStyleResolved={setStyleFallback}
        onFollowBroken={() => setFollowRef(null)}
      />
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
          fallback={styleFallback}
          onBasemap={(basemap) => updatePrefs({ basemap })}
          onGlobe={(globe) => updatePrefs({ globe })}
          onTerrain={(terrain) => updatePrefs({ terrain })}
        />
      </div>
      <Timeline replay={replay} disabled={!snapshot} />
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
    </div>
  );
}
