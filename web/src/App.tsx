import {
  type CSSProperties,
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Legend } from "./components/Legend";
import { MapControls } from "./components/MapControls";
import { hasWebGL2, MapFallback } from "./components/MapFallback";
import { Sidebar, type Tab } from "./components/Sidebar";
import { Timeline } from "./components/Timeline";
import { TopBar } from "./components/TopBar";
import { useLiveData } from "./live";
import type { Focus, LayerToggles, WindMode } from "./map/MapView";

// Карта с MapLibre — отдельный чанк: первый экран (панель, топбар) не ждёт её.
const MapView = lazy(() => import("./map/MapView").then((m) => ({ default: m.MapView })));

import { useI18n } from "./i18n";
import { BASEMAPS, type BasemapId, DEFAULT_BASEMAP } from "./map/style";
import { softwareGl } from "./map/webgl";
import { useReplay } from "./replay";
import { shareLink } from "./share";
import { buildSearch, parseUrlState, sameSearch, type MapView as UrlView } from "./urlState";

// Настройки карты живут в localStorage — только удобство, без них всё работает
const PREFS_KEY = "mc-map-prefs";
interface MapPrefs {
  basemap: BasemapId;
  globe: boolean;
  terrain: boolean;
  terrain3d: boolean;
  windMode: WindMode;
}
interface Toast {
  text: string;
  action?: { label: string; onClick: () => void }; // кнопка в тосте (например, «вернуть частицы»)
}
const reducedMotion = () =>
  typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
function loadPrefs(): MapPrefs {
  const prefs: MapPrefs = {
    basemap: DEFAULT_BASEMAP,
    globe: true,
    terrain: false,
    terrain3d: false,
    windMode: reducedMotion() || softwareGl() ? "arrows" : "particles",
  };
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    if (raw) {
      const saved = JSON.parse(raw) as Partial<MapPrefs>;
      if (saved.basemap && saved.basemap in BASEMAPS) prefs.basemap = saved.basemap;
      if (typeof saved.globe === "boolean") prefs.globe = saved.globe;
      if (typeof saved.terrain === "boolean") prefs.terrain = saved.terrain;
      if (typeof saved.terrain3d === "boolean") prefs.terrain3d = saved.terrain3d;
      if (saved.windMode === "particles" || saved.windMode === "arrows")
        prefs.windMode = saved.windMode;
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
const INITIAL_URL = parseUrlState(window.location.search); // ?s=…&view=…&basemap=…&at=…
const URL_SYNC_MS = 400; // при воспроизведении replayAt меняется каждые 400 мс — не спамим history

export function App() {
  const { t, lang } = useI18n();
  const replay = useReplay();
  const { snapshot, wind, windAvailable, error, fetchedAt, mode } = useLiveData(replay.replayAt);
  useEffect(() => replay.sync(snapshot, fetchedAt), [replay, snapshot, fetchedAt]);
  const [selectedRef, setSelectedRef] = useState<string | null>(INITIAL_URL.s);
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
  const [prefs, setPrefs] = useState<MapPrefs>(() => {
    const p = loadPrefs();
    if (INITIAL_URL.basemap) p.basemap = INITIAL_URL.basemap; // ссылка важнее сохранённого
    return p;
  });
  const [view, setView] = useState<UrlView | null>(INITIAL_URL.view);
  const [toast, setToast] = useState<Toast | null>(null);
  const [styleFallback, setStyleFallback] = useState(false);
  // Частицы выключены автоматически (устройство не тянет) — только на эту сессию:
  // в настройки не пишем, чтобы случайный провал не отключил их навсегда
  const [autoArrows, setAutoArrows] = useState(false);
  const [softGl] = useState(() => softwareGl());
  const windMode: WindMode = autoArrows ? "arrows" : prefs.windMode;
  const [sheetHeight, setSheetHeight] = useState(0); // видимая высота шторки на мобильном
  const updatePrefs = useCallback((patch: Partial<MapPrefs>) => {
    setPrefs((p) => {
      const next = { ...p, ...patch };
      savePrefs(next);
      return next;
    });
  }, []);

  // deep link: момент и груз применяем после первого живого снимка — он синхронизирует
  // серверные часы (replay.sync выше), иначе at из ссылки обрежется по часам клиента
  // и сервер ответит 400 (в моке с MOCK_TIME_SCALE часы расходятся на дни)
  const scrub = replay.scrub;
  const deepLinkApplied = useRef(false);
  useEffect(() => {
    if (!snapshot || deepLinkApplied.current) return;
    deepLinkApplied.current = true;
    if (INITIAL_URL.at) scrub(INITIAL_URL.at);
    if (!INITIAL_URL.s) return;
    const s = snapshot.shipments.find((x) => x.ref === INITIAL_URL.s);
    if (!s) {
      setSelectedRef(null);
      return;
    }
    setTab("shipments");
    if (!INITIAL_URL.view)
      setFocus({ lon: s.position.lon, lat: s.position.lat, zoom: 6, key: Date.now() });
  }, [snapshot, scrub]);

  // адрес отражает состояние: груз, вид, подложка, момент replay
  useEffect(() => {
    const t = setTimeout(() => {
      const next = buildSearch({
        s: selectedRef,
        view,
        basemap: prefs.basemap,
        at: replay.replayAt,
      });
      if (sameSearch(next, window.location.search)) return;
      window.history.replaceState(null, "", next ? `?${next}` : window.location.pathname);
    }, URL_SYNC_MS);
    return () => clearTimeout(t);
  }, [selectedRef, view, prefs.basemap, replay.replayAt]);

  useEffect(() => {
    document.title = selectedRef ? `${selectedRef} · Middle Corridor` : t("app.title");
  }, [selectedRef, t]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), toast.action ? 7000 : 2500);
    return () => clearTimeout(t);
  }, [toast]);

  const share = useCallback(async () => {
    const result = await shareLink(window.location.href, document.title);
    if (result === "copied") setToast({ text: t("toast.copied") });
    else if (result === "failed") setToast({ text: t("toast.shareFailed") });
  }, [t]);

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
              title={t("err.mapTitle")}
              detail={t("err.mapDetail", { message: err.message })}
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
              initialView={INITIAL_URL.view}
              onViewChange={setView}
              lang={lang}
              onSelectShipment={selectShipment}
              onSelectNode={selectNodeFromMap}
              onStyleResolved={setStyleFallback}
              onFollowBroken={() => setFollowRef(null)}
              windMode={windMode}
              onWindTooSlow={() => {
                setAutoArrows(true);
                setToast({
                  text: t("toast.particlesOff"),
                  action: { label: t("toast.particlesBack"), onClick: () => setAutoArrows(false) },
                });
              }}
            />
          </Suspense>
        </ErrorBoundary>
      ) : (
        <MapFallback title={t("err.noWebgl")} detail={t("err.noWebglDetail")} />
      )}
      <ErrorBoundary
        scope="управление"
        fallback={(_err, reset) => (
          <button type="button" className="ctrl-error" onClick={reset}>
            {t("err.controls")}
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
            software={softGl}
            windMode={windMode}
            windHint={autoArrows}
            onWindMode={(mode) => {
              setAutoArrows(false);
              updatePrefs({ windMode: mode });
            }}
          />
        </div>
        <Timeline replay={replay} disabled={!snapshot} />
      </ErrorBoundary>
      <ErrorBoundary
        scope="панель"
        fallback={(err, reset) => (
          <aside className="sidebar sidebar--error" role="alert">
            <div className="map-fallback">
              <div className="map-fallback__title">{t("err.panelTitle")}</div>
              <div className="map-fallback__detail">
                {t("err.panelDetail", { message: err.message })}
              </div>
              <button type="button" className="chip chip--on" onClick={reset}>
                {t("err.panelRetry")}
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
          onShare={share}
        />
      </ErrorBoundary>
      {toast && (
        <div className="toast" role="status">
          {toast.text}
          {toast.action && (
            <button
              type="button"
              className="toast__action"
              onClick={() => {
                toast.action?.onClick();
                setToast(null);
              }}
            >
              {toast.action.label}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
