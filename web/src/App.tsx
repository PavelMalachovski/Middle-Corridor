import { useCallback, useEffect, useState } from "react";
import { fetchSnapshot, fetchWind, type Snapshot, type WindField } from "./api";
import { MapView, type Focus, type LayerToggles } from "./map/MapView";
import { TopBar } from "./components/TopBar";
import { Legend } from "./components/Legend";
import { Sidebar, type Tab } from "./components/Sidebar";

const SNAPSHOT_MS = 10_000;
const WIND_MS = 60_000;

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
  const [, setTick] = useState(0); // перерисовка «N с назад» раз в секунду

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
        selectedRef={selectedRef}
        focus={focus}
        onSelectShipment={selectShipment}
        onSelectNode={selectNodeFromMap}
      />
      <TopBar
        snapshot={snapshot}
        error={error}
        fetchedAt={fetchedAt}
        layers={layers}
        windAvailable={windAvailable}
        onToggle={(key) => setLayers((l) => ({ ...l, [key]: !l[key] }))}
      />
      <Legend />
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
