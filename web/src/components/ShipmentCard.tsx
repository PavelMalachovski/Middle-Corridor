import type { Shipment, Snapshot } from "../api";
import { checkpointDelays } from "../forecast";
import {
  findNearestNode,
  fmtDir,
  fmtHours,
  fmtRelative,
  fmtTs,
  fmtWind,
  LEVEL_COLOR,
  LEVEL_ICON,
  levelLabel,
  levelOf,
} from "../format";
import { type Lang, nodeName, nodeNameByCode, useI18n } from "../i18n";
import { alertText, cargoLabel, eventLabel, holdLabel } from "../i18n/labels";
import { DelayChart } from "./charts/DelayChart";
import { StatePill } from "./ShipmentList";

interface Props {
  shipment: Shipment;
  snapshot: Snapshot;
  following: boolean;
  onBack: () => void;
  onFocus: () => void;
  onToggleFollow: () => void;
  onShare: () => void;
}

type T = (
  key: Parameters<ReturnType<typeof useI18n>["t"]>[0],
  params?: Record<string, string | number>,
) => string;

function positionText(
  s: Shipment,
  snapshot: Snapshot,
  t: T,
  lang: Lang,
): { title: string; detail: string } {
  const p = s.position;
  const name = (code: string | null | undefined) =>
    nodeNameByCode(snapshot.nodes, code, lang) || code || "";
  if (s.state === "delivered") {
    return {
      title: t("card.delivered", { node: name(s.destination_code) || s.destination }),
      detail: t("card.routeDone"),
    };
  }
  if (p.source === "event") {
    return {
      title: t("card.atNode", { node: name(p.from_code) }),
      detail: p.to_code ? t("card.confirmedNext", { node: name(p.to_code) }) : t("card.confirmed"),
    };
  }
  if (p.source === "ais") {
    const vessel = snapshot.vessels.find((v) => v.name === p.on_vessel);
    const sog = vessel?.sog != null ? `${vessel.sog.toFixed(1)} ${t("common.kn")}` : "";
    const age = vessel?.ts
      ? t("card.aisAge", { value: fmtRelative(vessel.ts, new Date(snapshot.generated_at)) })
      : "";
    return {
      title: t("card.onFerry", { vessel: p.on_vessel ?? "" }),
      detail: [`${name(p.from_code)} → ${name(p.to_code)}`, sog, age].filter(Boolean).join(" · "),
    };
  }
  const vehicle = p.on_vessel
    ? t("card.onVessel", { vessel: p.on_vessel })
    : p.mode === "sea"
      ? t("card.atSea")
      : t("card.byRail");
  return {
    title: t("card.legProgress", {
      from: name(p.from_code),
      to: name(p.to_code),
      pct: Math.round(p.leg_progress * 100),
    }),
    detail: t("card.estimate", { vehicle }),
  };
}

export function ShipmentCard({
  shipment: s,
  snapshot,
  following,
  onBack,
  onFocus,
  onToggleFollow,
  onShare,
}: Props) {
  const { t, lang } = useI18n();
  const ref = new Date(snapshot.generated_at);
  const pos = positionText(s, snapshot, t, lang);
  const near = findNearestNode(snapshot.nodes, s.position.lat, s.position.lon);
  const nearLevel = near ? levelOf(near) : "none";
  const hold = holdLabel(s, snapshot.nodes, lang);
  const place = (code: string | undefined, fallback: string) =>
    (code && nodeNameByCode(snapshot.nodes, code, lang)) || fallback;

  return (
    <div className="detail">
      <div className="detail__nav">
        <button type="button" className="link" onClick={onBack}>
          {t("card.all")}
        </button>
        <span className="detail__actions">
          <button type="button" className="link" onClick={onFocus}>
            {t("card.showOnMap")}
          </button>
          {s.state !== "delivered" && (
            <button
              type="button"
              className={`link ${following ? "link--active" : ""}`}
              onClick={onToggleFollow}
              title={t("card.followTitle")}
            >
              {following ? t("card.following") : t("card.follow")}
            </button>
          )}
          <button type="button" className="link" onClick={onShare} title={t("card.shareTitle")}>
            {t("card.share")}
          </button>
        </span>
      </div>
      <div className="card__head">
        <b className="mono detail__ref">{s.ref}</b>
        <StatePill shipment={s} />
      </div>
      <div className="detail__client">
        {s.client} · {cargoLabel(s)}
      </div>
      <div className="card__route detail__route">
        {place(s.origin_code, s.origin)} → {place(s.destination_code, s.destination)}
      </div>
      <div className="progress progress--lg">
        <div className="progress__bar" style={{ width: `${Math.round(s.progress * 100)}%` }} />
      </div>
      <div className="muted small">{t("card.progress", { pct: Math.round(s.progress * 100) })}</div>

      <section className="block">
        <div className="block__title">{t("card.now")}</div>
        <div className={`pos pos--${s.position.source}`}>
          <div className="pos__title">{pos.title}</div>
          <div className="muted small">{pos.detail}</div>
        </div>
        {hold && <div className="hold hold--lg">⚠ {hold}</div>}
        <dl className="kv">
          <dt>{t("card.lastEvent")}</dt>
          <dd>
            {eventLabel(s, snapshot.nodes, lang)}
            <div className="muted small">
              {fmtTs(s.last_event_at)} · {fmtRelative(s.last_event_at, ref)}
            </div>
          </dd>
          <dt>{s.state === "delivered" ? t("card.deliveredAt") : t("card.eta")}</dt>
          <dd>
            {fmtTs(s.eta)}
            <div className="muted small">
              {fmtRelative(s.eta, ref)}
              {s.delay_hours >= 1 && s.state !== "delivered" && (
                <span className="warn">
                  {" "}
                  · {t("card.delay", { value: fmtHours(s.delay_hours) })}
                </span>
              )}
            </div>
          </dd>
        </dl>
      </section>

      {near && (
        <section className="block">
          <div className="block__title">
            {t("card.weatherNear", { node: nodeName(near, lang) })}
          </div>
          <div className="weather">
            <span className="weather__level" style={{ color: LEVEL_COLOR[nearLevel] }}>
              {near.alert_level
                ? `${LEVEL_ICON[near.alert_level]} ${levelLabel(near.alert_level)}`
                : t("common.ok")}
            </span>
            <span>
              {fmtWind(near.wind_speed, near.wind_gust)} {fmtDir(near.wind_dir)}
            </span>
          </div>
          {alertText(near, lang) && <div className="muted small">{alertText(near, lang)}</div>}
          <div className="muted small">
            {t("card.updated", { value: fmtRelative(near.weather_ts, ref) })}
          </div>
        </section>
      )}

      <section className="block">
        <div className="block__title">{t("card.route")}</div>
        <DelayChart delays={checkpointDelays(s)} />
        <ol className="timeline">
          {s.checkpoints.map((cp) => (
            <li key={cp.code} className={`timeline__item timeline__item--${cp.state}`}>
              <span className="timeline__marker" />
              <div>
                <div className="timeline__name">{place(cp.code, cp.name)}</div>
                <div className="muted small">
                  {cp.actual_at
                    ? t("card.fact", { ts: fmtTs(cp.actual_at) })
                    : t("card.plan", {
                        ts: fmtTs(cp.planned_at),
                        rel: fmtRelative(cp.planned_at, ref),
                      })}
                </div>
              </div>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
