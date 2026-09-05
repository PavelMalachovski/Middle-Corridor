import type { NodeStatus, Snapshot } from "../api";
import {
  fmtDir,
  fmtRelative,
  fmtWind,
  LEVEL_COLOR,
  LEVEL_ICON,
  LEVEL_LABEL,
  levelOf,
  PAYLOAD_LABEL,
  REPORT_TITLE,
} from "../format";

const RANK: Record<string, number> = { critical: 0, warning: 1, watch: 2, ok: 3, none: 4 };

interface Props {
  snapshot: Snapshot;
  selectedNode: string | null;
  onFocusNode: (code: string) => void;
}

function NodeRow({
  node,
  selected,
  refDate,
  onClick,
}: {
  node: NodeStatus;
  selected: boolean;
  refDate: Date;
  onClick: () => void;
}) {
  const level = levelOf(node);
  return (
    <li>
      <button
        type="button"
        className={`card card--clickable ${selected ? "card--selected" : ""}`}
        onClick={onClick}
      >
        <div className="card__head">
          <b>{node.name}</b>
          <span
            className="pill"
            style={{ color: LEVEL_COLOR[level], borderColor: LEVEL_COLOR[level] }}
          >
            {node.alert_level
              ? `${LEVEL_ICON[node.alert_level]} ${LEVEL_LABEL[node.alert_level]}`
              : level === "ok"
                ? "норма"
                : "нет данных"}
          </span>
        </div>
        <div className="card__meta">
          <span>
            {fmtWind(node.wind_speed, node.wind_gust)} {fmtDir(node.wind_dir)}
          </span>
          <span className="muted">{node.country}</span>
        </div>
        {node.alert_message && <div className="muted small">{node.alert_message}</div>}
        {node.weather_ts && (
          <div className="muted small">обновлено {fmtRelative(node.weather_ts, refDate)}</div>
        )}
      </button>
    </li>
  );
}

export function PortsPanel({ snapshot, selectedNode, onFocusNode }: Props) {
  const refDate = new Date(snapshot.generated_at);
  const ports = snapshot.nodes
    .filter((n) => n.is_weather_tracked)
    .sort(
      (a, b) => RANK[levelOf(a)] - RANK[levelOf(b)] || (b.wind_speed ?? 0) - (a.wind_speed ?? 0),
    );
  const others = snapshot.nodes.filter((n) => !n.is_weather_tracked);
  const vessels = [...snapshot.vessels].sort(
    (a, b) => Number(b.has_recent_data) - Number(a.has_recent_data),
  );

  return (
    <div>
      <div className="block__title">Порты · погодный предиктор</div>
      <ul className="list">
        {ports.map((n) => (
          <NodeRow
            key={n.code}
            node={n}
            selected={n.code === selectedNode}
            refDate={refDate}
            onClick={() => onFocusNode(n.code)}
          />
        ))}
      </ul>

      <div className="block__title">Паромы Каспия</div>
      <ul className="list">
        {vessels.map((v) => (
          <li key={v.name} className="card">
            <div className="card__head">
              <b>{v.name}</b>
              {v.has_recent_data ? (
                <span className="pill pill--ais">AIS {fmtRelative(v.ts, refDate)}</span>
              ) : (
                <span className="pill pill--nodata">нет данных</span>
              )}
            </div>
            <div className="card__meta">
              <span>
                {v.has_recent_data ? `${v.route} · ${v.phase}` : "позиция вне AIS-покрытия"}
              </span>
              <span className="muted">{v.sog != null ? `${v.sog.toFixed(1)} уз` : v.operator}</span>
            </div>
          </li>
        ))}
      </ul>

      {snapshot.reports.length > 0 && (
        <>
          <div className="block__title">Сводки от доверенных источников</div>
          <ul className="list">
            {snapshot.reports.map((r) => (
              <li key={`${r.report_type}-${r.port_name}-${r.ts}`} className="card">
                <div className="card__head">
                  <b>
                    {REPORT_TITLE[r.report_type] ?? r.report_type}
                    {r.port_name ? ` — ${r.port_name}` : ""}
                  </b>
                  <span className="muted small">{fmtRelative(r.ts, refDate)}</span>
                </div>
                <dl className="kv kv--compact">
                  {Object.entries(r.payload).map(([k, v]) => (
                    <div key={k}>
                      <dt>{PAYLOAD_LABEL[k] ?? k}</dt>
                      <dd>{String(v)}</dd>
                    </div>
                  ))}
                </dl>
                {r.note && <div className="muted small">{r.note}</div>}
              </li>
            ))}
          </ul>
        </>
      )}

      <div className="block__title">Узлы без погоды</div>
      <ul className="chips">
        {others.map((n) => (
          <li key={n.code}>
            <button type="button" className="chip" onClick={() => onFocusNode(n.code)}>
              {n.name}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
