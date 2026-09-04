import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import type { Snapshot } from "../api";
import { ShipmentCard } from "./ShipmentCard";
import { ShipmentList } from "./ShipmentList";
import { PortsPanel } from "./PortsPanel";
import { NewsPanel } from "./NewsPanel";

export type Tab = "shipments" | "ports" | "news";

/**
 * На узких экранах сайдбар — шторка снизу с тремя положениями:
 * peek (только ручка и вкладки), half (пол-экрана), full (почти весь экран).
 * Тянется за ручку/вкладки (pointer events — палец и мышь), тап по ручке
 * сворачивает/разворачивает. Видимая высота отдаётся наверх, чтобы карта
 * учитывала её в отступах при подлёте.
 */
export type SheetState = "peek" | "half" | "full";

const MOBILE_QUERY = "(max-width: 900px)";
const SHEET_VH: Record<SheetState, number> = { peek: 0, half: 0.45, full: 0.88 };
const HEADER_PX = 64; // ручка + вкладки — столько остаётся видно в peek
const TAP_PX = 6;
const FLICK_PX_PER_MS = 0.4;

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

const fullHeight = () => window.innerHeight * SHEET_VH.full;
const visibleFor = (s: SheetState) =>
  s === "peek" ? HEADER_PX : window.innerHeight * SHEET_VH[s];
const offsetFor = (s: SheetState) => fullHeight() - visibleFor(s);
const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), hi);

interface Props {
  snapshot: Snapshot | null;
  error: string | null;
  tab: Tab;
  onTab: (tab: Tab) => void;
  selectedRef: string | null;
  selectedNode: string | null;
  onSelectShipment: (ref: string | null) => void;
  onFocusShipment: (ref: string) => void;
  onFocusNode: (code: string) => void;
  onSheetChange: (visiblePx: number) => void;
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
  selectedNode,
  onSelectShipment,
  onFocusShipment,
  onFocusNode,
  onSheetChange,
}: Props) {
  const mobile = useIsMobile();
  const [sheet, setSheet] = useState<SheetState>("half");
  const [dragOffset, setDragOffset] = useState<number | null>(null);
  const drag = useRef<DragInfo | null>(null);
  const lastDragEnd = useRef(0); // чтобы click после перетаскивания не переключал вкладку

  useEffect(() => {
    onSheetChange(mobile ? visibleFor(sheet) : 0);
  }, [mobile, sheet, onSheetChange]);

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
    const order: SheetState[] = ["full", "half", "peek"];
    const idx = order.indexOf(sheet);
    let next: SheetState;
    if (d.vy > FLICK_PX_PER_MS) {
      next = order[Math.min(idx + 1, order.length - 1)];
    } else if (d.vy < -FLICK_PX_PER_MS) {
      next = order[Math.max(idx - 1, 0)];
    } else {
      next = order.reduce((best, s) =>
        Math.abs(offsetFor(s) - offset) < Math.abs(offsetFor(best) - offset) ? s : best,
      );
    }
    setSheet(next);
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
              onBack={() => onSelectShipment(null)}
              onFocus={() => onFocusShipment(selected.ref)}
            />
          ) : (
            <ShipmentList snapshot={snapshot} onSelect={onFocusShipment} />
          )
        ) : tab === "ports" ? (
          <PortsPanel snapshot={snapshot} selectedNode={selectedNode} onFocusNode={onFocusNode} />
        ) : (
          <NewsPanel snapshot={snapshot} />
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
