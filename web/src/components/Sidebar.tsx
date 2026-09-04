import type { Snapshot } from "../api";
import { ShipmentCard } from "./ShipmentCard";
import { ShipmentList } from "./ShipmentList";
import { PortsPanel } from "./PortsPanel";
import { NewsPanel } from "./NewsPanel";

export type Tab = "shipments" | "ports" | "news";

interface Props {
  snapshot: Snapshot | null;
  tab: Tab;
  onTab: (tab: Tab) => void;
  selectedRef: string | null;
  selectedNode: string | null;
  onSelectShipment: (ref: string | null) => void;
  onFocusShipment: (ref: string) => void;
  onFocusNode: (code: string) => void;
}

export function Sidebar({
  snapshot,
  tab,
  onTab,
  selectedRef,
  selectedNode,
  onSelectShipment,
  onFocusShipment,
  onFocusNode,
}: Props) {
  const selected = snapshot?.shipments.find((s) => s.ref === selectedRef) ?? null;
  const alerts = snapshot?.nodes.filter((n) => n.alert_level).length ?? 0;
  const tabs: { key: Tab; label: string; count: number }[] = [
    { key: "shipments", label: "Грузы", count: snapshot?.shipments.length ?? 0 },
    { key: "ports", label: "Порты", count: alerts },
    { key: "news", label: "Новости", count: snapshot?.news.length ?? 0 },
  ];

  return (
    <aside className="sidebar">
      <nav className="tabs">
        {tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            className={`tab ${tab === t.key ? "tab--active" : ""}`}
            onClick={() => onTab(t.key)}
          >
            {t.label}
            {t.count > 0 && <span className="tab__count">{t.count}</span>}
          </button>
        ))}
      </nav>
      <div className="sidebar__body">
        {!snapshot ? (
          <div className="empty">Загружаем снимок коридора…</div>
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
