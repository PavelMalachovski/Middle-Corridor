import type { Snapshot } from "../api";
import type { LayerToggles } from "../map/MapView";

interface Props {
  snapshot: Snapshot | null;
  error: string | null;
  fetchedAt: Date | null;
  layers: LayerToggles;
  windAvailable: boolean;
  onToggle: (key: keyof LayerToggles) => void;
}

const TOGGLES: { key: keyof LayerToggles; label: string }[] = [
  { key: "shipments", label: "Грузы" },
  { key: "vessels", label: "Паромы" },
  { key: "wind", label: "Ветер" },
  { key: "routes", label: "Маршрут" },
];

export function TopBar({ snapshot, error, fetchedAt, layers, windAvailable, onToggle }: Props) {
  const ageSec = fetchedAt ? Math.max(0, Math.round((Date.now() - fetchedAt.getTime()) / 1000)) : null;
  const inTransit = snapshot?.shipments.filter((s) => s.state === "in_transit").length ?? 0;
  const delayed = snapshot?.shipments.filter((s) => s.delay_hours >= 1 && s.state !== "delivered").length ?? 0;
  const alerts =
    snapshot?.nodes.filter((n) => n.alert_level === "warning" || n.alert_level === "critical").length ?? 0;
  const errorCode = error?.match(/HTTP \d{3}/)?.[0] ?? null; // 404 = нет бэкенда, 5xx = упал

  return (
    <header className="topbar">
      <div className="topbar__brand">
        <div className="topbar__title">Middle Corridor</div>
        <div className="topbar__subtitle">карта статуса коридора</div>
      </div>
      {snapshot?.mock && (
        <span className="badge badge--mock" title="Синтетические данные для прототипа (MOCK_DATA=true)">
          MOCK DATA
        </span>
      )}
      <div className="topbar__kpis">
        <span className="kpi">
          <b>{inTransit}</b> в пути
        </span>
        <span className={`kpi ${delayed ? "kpi--warn" : ""}`}>
          <b>{delayed}</b> с задержкой
        </span>
        <span className={`kpi ${alerts ? "kpi--alert" : ""}`}>
          <b>{alerts}</b> {alerts === 1 ? "порт под риском" : "портов под риском"}
        </span>
      </div>
      <div className="topbar__layers">
        {TOGGLES.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            className={`chip ${layers[key] ? "chip--on" : ""}`}
            onClick={() => onToggle(key)}
            disabled={key === "wind" && !windAvailable}
            title={key === "wind" && !windAvailable ? "Поле ветра недоступно" : undefined}
          >
            {label}
          </button>
        ))}
      </div>
      <div className={`topbar__status ${error ? "topbar__status--error" : ""}`}>
        {error ? (
          <span title={error}>нет связи с API{errorCode ? ` · ${errorCode}` : ""}</span>
        ) : ageSec == null ? (
          <span>загрузка…</span>
        ) : (
          <span>
            <i className="dot-live" /> обновлено {ageSec} с назад
          </span>
        )}
      </div>
    </header>
  );
}
