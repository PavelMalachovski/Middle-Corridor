import { useEffect, useState } from "react";
import type { Snapshot } from "../api";
import type { LiveMode } from "../live";
import type { LayerToggles } from "../map/MapView";

const MODE_LABEL: Record<LiveMode, string> = { stream: "поток", poll: "поллинг", replay: "replay" };

interface Props {
  snapshot: Snapshot | null;
  error: string | null;
  fetchedAt: Date | null;
  mode: LiveMode;
  layers: LayerToggles;
  windAvailable: boolean;
  onToggle: (key: keyof LayerToggles) => void;
}

const TOGGLES: { key: keyof LayerToggles; label: string }[] = [
  { key: "shipments", label: "Грузы" },
  { key: "vessels", label: "Паромы" },
  { key: "wind", label: "Ветер" },
  { key: "routes", label: "Коридор" },
];

export function TopBar({ snapshot, error, fetchedAt, mode, layers, windAvailable, onToggle }: Props) {
  const [, setTick] = useState(0); // перерисовка «N с назад» раз в секунду
  useEffect(() => {
    const t = setInterval(() => setTick((v) => v + 1), 1000);
    return () => clearInterval(t);
  }, []);
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
            <i className="dot-live" /> обновлено {ageSec} с назад · {MODE_LABEL[mode]}
          </span>
        )}
      </div>
    </header>
  );
}
