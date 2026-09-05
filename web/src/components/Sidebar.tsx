import {
  lazy,
  type PointerEvent as ReactPointerEvent,
  Suspense,
  useEffect,
  useRef,
  useState,
} from "react";
import type { Snapshot } from "../api";
import { ShipmentCard } from "./ShipmentCard";
import { ShipmentList } from "./ShipmentList";

export type Tab = "shipments" | "ports" | "news";

import { EMPTY_FILTER, type ShipmentFilter } from "../shipmentFilter";
/**
 * На узких экранах сайдбар — шторка снизу с тремя положениями:
 * peek (только ручка и вкладки), half (пол-экрана), full (почти весь экран).
 * Тянется за ручку/вкладки (pointer events — палец и мышь), тап по ручке
 * сворачивает/разворачивает. Видимая высота отдаётся наверх, чтобы карта
 * учитывала её в отступах при подлёте.
 */
import {
  clamp,
  HEADER_PX,
  type SheetState,
  fullHeight as sheetFullHeight,
  offsetFor as sheetOffsetFor,
  visibleFor as sheetVisibleFor,
  snapSheet,
} from "./sheet";

// Вкладки, которые открывают не первыми, — отдельные чанки
const PortsPanel = lazy(() => import("./PortsPanel").then((m) => ({ default: m.PortsPanel })));
const NewsPanel = lazy(() => import("./NewsPanel").then((m) => ({ default: m.NewsPanel })));
const PanelLoading = () => <div className="muted small panel-loading">загрузка…</div>;

export type { SheetState } from "./sheet";

const MOBILE_QUERY = "(max-width: 900px)";
const TAP_PX = 6;

/**
 * Высота окна для геометрии шторки. CSS-единица vh на телефоне считается от
 * максимального окна (адресная строка скрыта), а innerHeight — от текущего;
 * если высоту задать в vh, а положение считать в JS, шторка в «peek» торчит
 * выше расчётного и накрывает шкалу времени. Поэтому всё — от innerHeight.
 */
function useViewportHeight(): number {
  const [h, setH] = useState(() => window.innerHeight);
  useEffect(() => {
    const update = () => setH(window.innerHeight);
    window.addEventListener("resize", update);
    window.visualViewport?.addEventListener("resize", update);
    return () => {
      window.removeEventListener("resize", update);
      window.visualViewport?.removeEventListener("resize", update);
    };
  }, []);
  return h;
}

function useIsMobile(): boolean {
  const [mobile, setMobile] = useState(() => window.matchMedia(MOBILE_QUERY).matches);
  useEffect(() => {
    const mq = window.matchMedia(MOBILE_QUERY);
    const onChange = (e: MediaQueryListEvent) => setMobile(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return mobile;
}

const fullHeight = () => sheetFullHeight(window.innerHeight);
const visibleFor = (s: SheetState) => sheetVisibleFor(s, window.innerHeight);
const offsetFor = (s: SheetState) => sheetOffsetFor(s, window.innerHeight);

interface Props {
  snapshot: Snapshot | null;
  error: string | null;
  tab: Tab;
  onTab: (tab: Tab) => void;
  selectedRef: string | null;
  followRef: string | null;
  selectedNode: string | null;
  onSelectShipment: (ref: string | null) => void;
  onToggleFollow: (ref: string) => void;
  onFocusShipment: (ref: string) => void;
  onFocusNode: (code: string) => void;
  onSheetChange: (visiblePx: number) => void;
  onShare: () => void;
}

interface DragInfo {
  target: HTMLElement; // что было под пальцем в момент касания
  startY: number;
  startOffset: number;
  lastY: number;
  lastT: number;
  vy: number; // px/ms, вниз > 0
  moved: boolean;
}

export function Sidebar({
  snapshot,
  error,
  tab,
  onTab,
  selectedRef,
  followRef,
  selectedNode,
  onSelectShipment,
  onToggleFollow,
  onFocusShipment,
  onFocusNode,
  onSheetChange,
  onShare,
}: Props) {
  const mobile = useIsMobile();
  const [filter, setFilter] = useState<ShipmentFilter>(EMPTY_FILTER);
  const viewportH = useViewportHeight();
  const [sheet, setSheet] = useState<SheetState>("half");
  const [dragOffset, setDragOffset] = useState<number | null>(null);
  const drag = useRef<DragInfo | null>(null);
  const lastDragEnd = useRef(0); // чтобы click после перетаскивания не переключал вкладку

  useEffect(() => {
    onSheetChange(mobile ? visibleFor(sheet) : 0);
  }, [mobile, sheet, onSheetChange, viewportH]);

  const selectTab = (t: Tab) => {
    onTab(t);
    if (mobile && sheet === "peek") setSheet("half");
  };

  // Захват указателя с самого касания: при быстром свайпе первый pointermove
  // уже за пределами заголовка, без захвата жест теряется. Побочный эффект —
  // click после захвата уходит заголовку, а не кнопке, поэтому тапы по
  // вкладкам и ручке разбираем здесь же по цели касания.
  const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!mobile) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = {
      target: e.target as HTMLElement,
      startY: e.clientY,
      startOffset: offsetFor(sheet),
      lastY: e.clientY,
      lastT: performance.now(),
      vy: 0,
      moved: false,
    };
  };

  const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    if (!d) return;
    const dy = e.clientY - d.startY;
    if (!d.moved && Math.abs(dy) > TAP_PX) d.moved = true;
    if (!d.moved) return;
    const now = performance.now();
    d.vy = (e.clientY - d.lastY) / Math.max(now - d.lastT, 1);
    d.lastY = e.clientY;
    d.lastT = now;
    setDragOffset(clamp(d.startOffset + dy, 0, fullHeight() - HEADER_PX));
  };

  const onPointerUp = (e: ReactPointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    if (!d) return;
    drag.current = null;
    setDragOffset(null);
    if (!d.moved) {
      const tabButton = d.target.closest<HTMLElement>("[data-tab]");
      if (tabButton) selectTab(tabButton.dataset.tab as Tab);
      else if (d.target.closest(".sheet-handle")) setSheet(sheet === "peek" ? "half" : "peek");
      return;
    }
    lastDragEnd.current = performance.now();
    const offset = clamp(d.startOffset + (e.clientY - d.startY), 0, fullHeight() - HEADER_PX);
    setSheet(snapSheet(sheet, offset, d.vy, window.innerHeight));
  };

  // Клик остаётся для клавиатуры и десктопа; на мобильном после захвата он
  // приходит заголовку, а хвост перетаскивания — отсекаем по времени.
  const onTabClick = (t: Tab) => {
    if (performance.now() - lastDragEnd.current < 300) return;
    selectTab(t);
  };

  const selected = snapshot?.shipments.find((s) => s.ref === selectedRef) ?? null;
  const alerts = snapshot?.nodes.filter((n) => n.alert_level).length ?? 0;
  const tabs: { key: Tab; label: string; count: number }[] = [
    { key: "shipments", label: "Грузы", count: snapshot?.shipments.length ?? 0 },
    { key: "ports", label: "Порты", count: alerts },
    { key: "news", label: "Новости", count: snapshot?.news.length ?? 0 },
  ];

  const style = mobile
    ? {
        height: `${fullHeight()}px`, // от innerHeight, как и translateY — не 88vh
        transform: `translateY(${dragOffset ?? offsetFor(sheet)}px)`,
        transition: dragOffset != null ? "none" : undefined,
      }
    : undefined;

  return (
    <aside className={`sidebar ${mobile ? `sidebar--sheet sidebar--${sheet}` : ""}`} style={style}>
      <div
        className="sheet-header"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        <div className="sheet-handle" aria-hidden="true">
          <span />
        </div>
        <nav className="tabs">
          {tabs.map((t) => (
            <button
              key={t.key}
              type="button"
              data-tab={t.key}
              className={`tab ${tab === t.key ? "tab--active" : ""}`}
              onClick={() => onTabClick(t.key)}
            >
              {t.label}
              {t.count > 0 && <span className="tab__count">{t.count}</span>}
            </button>
          ))}
        </nav>
      </div>
      <div className="sidebar__body">
        {!snapshot ? (
          error ? (
            <ApiError error={error} />
          ) : (
            <div className="empty">Загружаем снимок коридора…</div>
          )
        ) : tab === "shipments" ? (
          selected ? (
            <ShipmentCard
              shipment={selected}
              snapshot={snapshot}
              following={followRef === selected.ref}
              onBack={() => onSelectShipment(null)}
              onFocus={() => onFocusShipment(selected.ref)}
              onToggleFollow={() => onToggleFollow(selected.ref)}
              onShare={onShare}
            />
          ) : (
            <ShipmentList
              snapshot={snapshot}
              filter={filter}
              onFilter={setFilter}
              onSelect={onFocusShipment}
            />
          )
        ) : tab === "ports" ? (
          <Suspense fallback={<PanelLoading />}>
            <PortsPanel snapshot={snapshot} selectedNode={selectedNode} onFocusNode={onFocusNode} />
          </Suspense>
        ) : (
          <Suspense fallback={<PanelLoading />}>
            <NewsPanel snapshot={snapshot} />
          </Suspense>
        )}
      </div>
    </aside>
  );
}

function ApiError({ error }: { error: string }) {
  const code = error.match(/HTTP (\d{3})/)?.[1];
  const hint =
    code === "404"
      ? "На этом домене нет бэкенда: фронт задеплоен отдельно (Root Directory = web?), а VITE_API_BASE не задан."
      : code === "503"
        ? "Бэкенд жив, но источник данных недоступен. На Vercel-демо: MOCK_DATA=true в Environment Variables и Redeploy."
        : code?.startsWith("5")
          ? "Бэкенд падает при запросе. На Vercel: проверь MOCK_DATA=true и логи функции (Deployments → Functions)."
          : "Сервер не отвечает или блокирует запрос (сеть, CORS).";
  return (
    <div className="empty empty--error">
      <div>
        <b>API не отвечает</b>
      </div>
      <div className="mono small">{error}</div>
      <div className="small">{hint}</div>
    </div>
  );
}
