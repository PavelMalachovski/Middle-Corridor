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
  LEVEL_LABEL,
  levelOf,
} from "../format";
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

function positionText(s: Shipment, snapshot: Snapshot): { title: string; detail: string } {
  const p = s.position;
  const nodeName = (code: string | null) =>
    snapshot.nodes.find((n) => n.code === code)?.name ?? code ?? "";
  if (s.state === "delivered") {
    return { title: `Доставлен: ${s.destination}`, detail: "Маршрут завершён" };
  }
  if (p.source === "event") {
    return {
      title: `В узле ${nodeName(p.from_code)}`,
      detail: p.to_code
        ? `Подтверждено событием · далее ${nodeName(p.to_code)}`
        : "Подтверждено событием",
    };
  }
  if (p.source === "ais") {
    const vessel = snapshot.vessels.find((v) => v.name === p.on_vessel);
    const sog = vessel?.sog != null ? `${vessel.sog.toFixed(1)} уз` : "";
    const age = vessel?.ts ? `AIS ${fmtRelative(vessel.ts, new Date(snapshot.generated_at))}` : "";
    return {
      title: `На пароме «${p.on_vessel}»`,
      detail: [`${nodeName(p.from_code)} → ${nodeName(p.to_code)}`, sog, age]
        .filter(Boolean)
        .join(" · "),
    };
  }
  const vehicle = p.on_vessel
    ? `на судне «${p.on_vessel}»`
    : p.mode === "sea"
      ? "в море"
      : "по железной дороге";
  return {
    title: `${nodeName(p.from_code)} → ${nodeName(p.to_code)}, ${Math.round(p.leg_progress * 100)}% плеча`,
    detail: `Оценка по расписанию (${vehicle}) — живой позиции нет`,
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
  const ref = new Date(snapshot.generated_at);
  const pos = positionText(s, snapshot);
  const near = findNearestNode(snapshot.nodes, s.position.lat, s.position.lon);
  const nearLevel = near ? levelOf(near) : "none";

  return (
    <div className="detail">
      <div className="detail__nav">
        <button type="button" className="link" onClick={onBack}>
          ← все грузы
        </button>
        <span className="detail__actions">
          <button type="button" className="link" onClick={onFocus}>
            показать на карте
          </button>
          {s.state !== "delivered" && (
            <button
              type="button"
              className={`link ${following ? "link--active" : ""}`}
              onClick={onToggleFollow}
              title="Камера едет за грузом; любое движение карты снимает слежение"
            >
              {following ? "◉ следим" : "◎ следить"}
            </button>
          )}
          <button
            type="button"
            className="link"
            onClick={onShare}
            title="Ссылка откроет этот груз в этом же месте карты"
          >
            ⇪ поделиться
          </button>
        </span>
      </div>
      <div className="card__head">
        <b className="mono detail__ref">{s.ref}</b>
        <StatePill shipment={s} />
      </div>
      <div className="detail__client">
        {s.client} · {s.cargo}
      </div>
      <div className="card__route detail__route">
        {s.origin} → {s.destination}
      </div>
      <div className="progress progress--lg">
        <div className="progress__bar" style={{ width: `${Math.round(s.progress * 100)}%` }} />
      </div>
      <div className="muted small">{Math.round(s.progress * 100)}% маршрута</div>

      <section className="block">
        <div className="block__title">Сейчас</div>
        <div className={`pos pos--${s.position.source}`}>
          <div className="pos__title">{pos.title}</div>
          <div className="muted small">{pos.detail}</div>
        </div>
        {s.hold_reason && <div className="hold hold--lg">⚠ {s.hold_reason}</div>}
        <dl className="kv">
          <dt>Последнее событие</dt>
          <dd>
            {s.last_event}
            <div className="muted small">
              {fmtTs(s.last_event_at)} · {fmtRelative(s.last_event_at, ref)}
            </div>
          </dd>
          <dt>{s.state === "delivered" ? "Доставлен" : "ETA"}</dt>
          <dd>
            {fmtTs(s.eta)}
            <div className="muted small">
              {fmtRelative(s.eta, ref)}
              {s.delay_hours >= 1 && s.state !== "delivered" && (
                <span className="warn"> · задержка {fmtHours(s.delay_hours)}</span>
              )}
            </div>
          </dd>
        </dl>
      </section>

      {near && (
        <section className="block">
          <div className="block__title">Погода рядом · {near.name}</div>
          <div className="weather">
            <span className="weather__level" style={{ color: LEVEL_COLOR[nearLevel] }}>
              {near.alert_level
                ? `${LEVEL_ICON[near.alert_level]} ${LEVEL_LABEL[near.alert_level]}`
                : "норма"}
            </span>
            <span>
              {fmtWind(near.wind_speed, near.wind_gust)} {fmtDir(near.wind_dir)}
            </span>
          </div>
          {near.alert_message && <div className="muted small">{near.alert_message}</div>}
          <div className="muted small">обновлено {fmtRelative(near.weather_ts, ref)}</div>
        </section>
      )}

      <section className="block">
        <div className="block__title">Маршрут · отклонение от плана по узлам, ч</div>
        <DelayChart delays={checkpointDelays(s)} />
        <ol className="timeline">
          {s.checkpoints.map((cp) => (
            <li key={cp.code} className={`timeline__item timeline__item--${cp.state}`}>
              <span className="timeline__marker" />
              <div>
                <div className="timeline__name">{cp.name}</div>
                <div className="muted small">
                  {cp.actual_at
                    ? `факт ${fmtTs(cp.actual_at)}`
                    : `план ${fmtTs(cp.planned_at)} · ${fmtRelative(cp.planned_at, ref)}`}
                </div>
              </div>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
