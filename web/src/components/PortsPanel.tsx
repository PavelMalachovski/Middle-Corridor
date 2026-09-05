import type { NodeStatus, Snapshot, Thresholds } from "../api";
import { fmtIn, portOutlook } from "../forecast";
import {
  fmtDir,
  fmtRelative,
  fmtTs,
  fmtWind,
  LEVEL_COLOR,
  LEVEL_ICON,
  levelLabel,
  levelOf,
  payloadLabel,
  reportTitle,
} from "../format";
import { type Lang, nodeName, nodeNameByCode, useI18n } from "../i18n";
import { alertText, reportPort, vesselPhase, vesselRoute } from "../i18n/labels";
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
  const { t } = useI18n();
  if (!node.forecast?.length) return null;
  const o = portOutlook(node.forecast, thresholds, now);
  const at = (iso: string) => fmtTs(iso).replace(" UTC", "");
  if (o.closedNow) {
    return (
      <div className="outlook outlook--closed">
        {t("outlook.closed")} ·{" "}
        {o.opensAt ? t("outlook.opensAt", { ts: at(o.opensAt) }) : t("outlook.noOpen")}
      </div>
    );
  }
  if (o.stopsAt) {
    return (
      <div className="outlook outlook--soon">
        {t("outlook.stops", { rel: fmtIn(o.stopsAt, now), ts: at(o.stopsAt) })}
        {o.opensAt ? ` · ${t("outlook.opensAt", { ts: at(o.opensAt) })}` : ""}
      </div>
    );
  }
  return (
    <div className="outlook outlook--ok">
      {t("outlook.calm")}
      {o.peak
        ? ` · ${t("outlook.peak", { speed: o.peak.speed.toFixed(0), rel: fmtIn(o.peak.ts, now) })}`
        : ""}
    </div>
  );
}

function NodeRow({
  node,
  selected,
  refDate,
  thresholds,
  lang,
  onClick,
}: {
  node: NodeStatus;
  selected: boolean;
  refDate: Date;
  thresholds: Thresholds;
  lang: Lang;
  onClick: () => void;
}) {
  const { t } = useI18n();
  const level = levelOf(node);
  const alert = alertText(node, lang);
  return (
    <li>
      <button
        type="button"
        className={`card card--clickable ${selected ? "card--selected" : ""}`}
        onClick={onClick}
      >
        <div className="card__head">
          <b>{nodeName(node, lang)}</b>
          <span
            className="pill"
            style={{ color: LEVEL_COLOR[level], borderColor: LEVEL_COLOR[level] }}
          >
            {node.alert_level
              ? `${LEVEL_ICON[node.alert_level]} ${levelLabel(node.alert_level)}`
              : level === "ok"
                ? t("common.ok")
                : t("common.noData")}
          </span>
        </div>
        <div className="card__meta">
          <span>
            {fmtWind(node.wind_speed, node.wind_gust)} {fmtDir(node.wind_dir)}
          </span>
          <span className="muted">
            {lang === "en" && node.country_en ? node.country_en : node.country}
          </span>
        </div>
        {alert && <div className="muted small">{alert}</div>}
        <OutlookLine node={node} thresholds={thresholds} now={refDate} />
        {selected && node.forecast && node.forecast.length > 1 && (
          <WindSparkline forecast={node.forecast} thresholds={thresholds} now={refDate} />
        )}
        {node.weather_ts && (
          <div className="muted small">
            {t("ports.updated", { value: fmtRelative(node.weather_ts, refDate) })}
          </div>
        )}
      </button>
    </li>
  );
}

export function PortsPanel({ snapshot, selectedNode, onFocusNode }: Props) {
  const { t, lang } = useI18n();
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
      <div className="block__title">{t("ports.title")}</div>
      <ul className="list">
        {ports.map((n) => (
          <NodeRow
            key={n.code}
            node={n}
            selected={n.code === selectedNode}
            refDate={refDate}
            thresholds={snapshot.thresholds}
            lang={lang}
            onClick={() => onFocusNode(n.code)}
          />
        ))}
      </ul>

      <div className="block__title">{t("ports.ferries")}</div>
      <ul className="list">
        {vessels.map((v) => (
          <li key={v.name} className="card">
            <div className="card__head">
              <b>{v.name}</b>
              {v.has_recent_data ? (
                <span className="pill pill--ais">AIS {fmtRelative(v.ts, refDate)}</span>
              ) : (
                <span className="pill pill--nodata">{t("common.noData")}</span>
              )}
            </div>
            <div className="card__meta">
              <span>
                {v.has_recent_data
                  ? `${vesselRoute(v, snapshot.nodes, lang)} · ${vesselPhase(v, snapshot.nodes, lang)}`
                  : t("ports.outsideAis")}
              </span>
              <span className="muted">
                {v.sog != null ? `${v.sog.toFixed(1)} ${t("common.kn")}` : v.operator}
              </span>
            </div>
          </li>
        ))}
      </ul>

      {snapshot.reports.length > 0 && (
        <>
          <div className="block__title">{t("ports.reports")}</div>
          <ul className="list">
            {snapshot.reports.map((r) => {
              const port = reportPort(r, snapshot.nodes, lang);
              return (
                <li key={`${r.report_type}-${r.port_name}-${r.ts}`} className="card">
                  <div className="card__head">
                    <b>
                      {reportTitle(r.report_type)}
                      {port ? ` — ${port}` : ""}
                    </b>
                    <span className="muted small">{fmtRelative(r.ts, refDate)}</span>
                  </div>
                  <dl className="kv kv--compact">
                    {Object.entries(r.payload)
                      .filter(([k]) => k !== "border_code")
                      .map(([k, v]) => (
                        <div key={k}>
                          <dt>{payloadLabel(k)}</dt>
                          <dd>
                            {k === "border" && typeof r.payload.border_code === "string"
                              ? nodeNameByCode(snapshot.nodes, r.payload.border_code, lang)
                              : String(v)}
                          </dd>
                        </div>
                      ))}
                  </dl>
                  {r.note && <div className="muted small">{r.note}</div>}
                </li>
              );
            })}
          </ul>
        </>
      )}

      <div className="block__title">{t("ports.otherNodes")}</div>
      <ul className="chips">
        {others.map((n) => (
          <li key={n.code}>
            <button type="button" className="chip" onClick={() => onFocusNode(n.code)}>
              {nodeName(n, lang)}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
