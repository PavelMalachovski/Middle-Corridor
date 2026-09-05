import type { Shipment, Snapshot } from "../api";
import { fmtHours, fmtRelative, STATE_LABEL } from "../format";
import {
  EMPTY_FILTER,
  filterShipments,
  isFilterActive,
  LEG_OPTIONS,
  type ShipmentFilter,
  STATUS_OPTIONS,
} from "../shipmentFilter";

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
  filter,
  onFilter,
  onSelect,
}: {
  snapshot: Snapshot;
  filter: ShipmentFilter;
  onFilter: (f: ShipmentFilter) => void;
  onSelect: (ref: string) => void;
}) {
  const ref = new Date(snapshot.generated_at);
  const all = [...snapshot.shipments].sort(
    (a, b) => ORDER[a.state] - ORDER[b.state] || b.delay_hours - a.delay_hours,
  );
  if (!all.length) {
    return (
      <div className="empty">
        Отправок нет: источник трекинга ещё не подключён. Порты, суда и новости — на соседних
        вкладках.
      </div>
    );
  }
  const items = filterShipments(all, filter, snapshot.nodes);
  const active = isFilterActive(filter);
  return (
    <>
      <div className="filters">
        <input
          type="search"
          className="search"
          placeholder="Номер, клиент, груз, город…"
          aria-label="Поиск груза"
          value={filter.query}
          onChange={(e) => onFilter({ ...filter, query: e.target.value })}
        />
        <div className="filters__row" role="group" aria-label="Статус">
          {STATUS_OPTIONS.map((o) => (
            <button
              key={o.key}
              type="button"
              className={`chip chip--sm ${filter.status === o.key ? "chip--on" : ""}`}
              onClick={() => onFilter({ ...filter, status: o.key })}
            >
              {o.label}
            </button>
          ))}
        </div>
        <div className="filters__row">
          <select
            className="select"
            aria-label="Плечо коридора"
            value={filter.leg}
            onChange={(e) => onFilter({ ...filter, leg: e.target.value as ShipmentFilter["leg"] })}
          >
            {LEG_OPTIONS.map((o) => (
              <option key={o.key} value={o.key}>
                {o.label}
              </option>
            ))}
          </select>
          {active && (
            <button type="button" className="link" onClick={() => onFilter(EMPTY_FILTER)}>
              сбросить · {items.length} из {all.length}
            </button>
          )}
        </div>
      </div>
      {!items.length && (
        <div className="empty">
          Ничего не найдено.{" "}
          <button type="button" className="link" onClick={() => onFilter(EMPTY_FILTER)}>
            Сбросить фильтры
          </button>
        </div>
      )}
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
    </>
  );
}
