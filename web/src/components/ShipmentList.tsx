import type { Shipment, Snapshot } from "../api";
import { fmtHours, fmtRelative, STATE_LABEL } from "../format";

const ORDER: Record<Shipment["state"], number> = {
  waiting: 0,
  in_transit: 1,
  planned: 2,
  delivered: 3,
};

export function StatePill({ shipment }: { shipment: Shipment }) {
  const delayed = shipment.delay_hours >= 1 && shipment.state !== "delivered";
  return (
    <span className={`pill pill--${shipment.state} ${delayed ? "pill--delayed" : ""}`}>
      {STATE_LABEL[shipment.state]}
      {delayed && ` · +${fmtHours(shipment.delay_hours)}`}
    </span>
  );
}

export function ShipmentList({
  snapshot,
  onSelect,
}: {
  snapshot: Snapshot;
  onSelect: (ref: string) => void;
}) {
  const ref = new Date(snapshot.generated_at);
  const items = [...snapshot.shipments].sort(
    (a, b) => ORDER[a.state] - ORDER[b.state] || b.delay_hours - a.delay_hours,
  );
  if (!items.length) {
    return (
      <div className="empty">
        Отправок нет: источник трекинга ещё не подключён. Порты, суда и новости — на соседних
        вкладках.
      </div>
    );
  }
  return (
    <ul className="list">
      {items.map((s) => (
        <li key={s.ref}>
          <button type="button" className="card card--clickable" onClick={() => onSelect(s.ref)}>
            <div className="card__head">
              <b className="mono">{s.ref}</b>
              <StatePill shipment={s} />
            </div>
            <div className="card__route">
              {s.origin} → {s.destination}
            </div>
            <div className="progress">
              <div
                className="progress__bar"
                style={{ width: `${Math.round(s.progress * 100)}%` }}
              />
            </div>
            <div className="card__meta">
              <span>{s.last_event}</span>
              <span className="muted">{fmtRelative(s.last_event_at, ref)}</span>
            </div>
            {s.hold_reason && <div className="hold">⚠ {s.hold_reason}</div>}
          </button>
        </li>
      ))}
    </ul>
  );
}
