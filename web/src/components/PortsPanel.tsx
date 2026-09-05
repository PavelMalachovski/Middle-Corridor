import type { NodeStatus, Snapshot, Thresholds } from "../api";
import { fmtIn, portOutlook } from "../forecast";
import {
  fmtDir,
  fmtRelative,
  fmtTs,
  fmtWind,
  LEVEL_COLOR,
  LEVEL_ICON,
  LEVEL_LABEL,
  levelOf,
  PAYLOAD_LABEL,
  REPORT_TITLE,
} from "../format";
import { WindSparkline } from "./charts/Sparkline";

const RANK: Record<string, number> = { critical: 0, warning: 1, watch: 2, ok: 3, none: 4 };

interface Props {
  snapshot: Snapshot;
  selectedNode: string | null;
  onFocusNode: (code: string) => void;
}

/** Одна строка про ближайшие 48 часов: встанет / откроется / без остановок. */
function OutlookLine({
  node,
  thresholds,
  now,
}: {
  node: NodeStatus;
  thresholds: Thresholds;
  now: Date;
}) {
  if (!node.forecast?.length) return null;
  const o = portOutlook(node.forecast, thresholds, now);
  const at = (iso: string) => fmtTs(iso).replace(" UTC", "");
  if (o.closedNow) {
    return (
      <div className="outlook outlook--closed">
        ● порт закрыт по ветру
        {o.opensAt ? ` · откроется к ${at(o.opensAt)}` : " · в ближайшие 48 ч не откроется"}
      </div>
    );
  }
  if (o.stopsAt) {
    return (
      <div className="outlook outlook--soon">
        ▲ встанет {fmtIn(o.stopsAt, now)} ({at(o.stopsAt)})
        {o.opensAt ? ` · откроется к ${at(o.opensAt)}` : ""}
      </div>
    );
  }
  return (
    <div className="outlook outlook--ok">
      ○ остановок в ближайшие 48 ч не ожидается
      {o.peak ? ` · пик ${o.peak.speed.toFixed(0)} м/с ${fmtIn(o.peak.ts, now)}` : ""}
    </div>
  );
}

function NodeRow({
  node,
  selected,
  refDate,
  thresholds,
  onClick,
}: {
  node: NodeStatus;
  selected: boolean;
  refDate: Date;
  thresholds: Thresholds;
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
        <OutlookLine node={node} thresholds={thresholds} now={refDate} />
        {selected && node.forecast && node.forecast.length > 1 && (
          <WindSparkline forecast={node.forecast} thresholds={thresholds} now={refDate} />
        )}
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
            thresholds={snapshot.thresholds}
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
