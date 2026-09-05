import type { Shipment, Snapshot } from "../api";
import { fmtHours, fmtRelative, stateLabel } from "../format";
import { type Key, nodeNameByCode, useI18n } from "../i18n";
import { eventLabel, holdLabel } from "../i18n/labels";
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
      {stateLabel(shipment.state)}
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
  const { t, lang } = useI18n();
  const ref = new Date(snapshot.generated_at);
  const all = [...snapshot.shipments].sort(
    (a, b) => ORDER[a.state] - ORDER[b.state] || b.delay_hours - a.delay_hours,
  );
  if (!all.length) {
    return <div className="empty">{t("list.empty")}</div>;
  }
  const items = filterShipments(all, filter, snapshot.nodes);
  const active = isFilterActive(filter);
  const place = (code: string | undefined, fallback: string) =>
    (code && nodeNameByCode(snapshot.nodes, code, lang)) || fallback;
  return (
    <>
      <div className="filters">
        <input
          type="search"
          className="search"
          placeholder={t("list.searchPlaceholder")}
          aria-label={t("list.searchLabel")}
          value={filter.query}
          onChange={(e) => onFilter({ ...filter, query: e.target.value })}
        />
        <fieldset className="filters__row">
          <legend className="sr-only">{t("list.statusLabel")}</legend>
          {STATUS_OPTIONS.map((key) => (
            <button
              key={key}
              type="button"
              className={`chip chip--sm ${filter.status === key ? "chip--on" : ""}`}
              onClick={() => onFilter({ ...filter, status: key })}
            >
              {t(`filter.status.${key}` as Key)}
            </button>
          ))}
        </fieldset>
        <div className="filters__row">
          <select
            className="select"
            aria-label={t("list.legLabel")}
            value={filter.leg}
            onChange={(e) => onFilter({ ...filter, leg: e.target.value as ShipmentFilter["leg"] })}
          >
            {LEG_OPTIONS.map((key) => (
              <option key={key} value={key}>
                {t(`filter.leg.${key}` as Key)}
              </option>
            ))}
          </select>
          {active && (
            <button type="button" className="link" onClick={() => onFilter(EMPTY_FILTER)}>
              {t("list.resetCount", { shown: items.length, total: all.length })}
            </button>
          )}
        </div>
      </div>
      {!items.length && (
        <div className="empty">
          {t("list.nothingFound")}{" "}
          <button type="button" className="link" onClick={() => onFilter(EMPTY_FILTER)}>
            {t("list.resetFilters")}
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
                {place(s.origin_code, s.origin)} → {place(s.destination_code, s.destination)}
              </div>
              <div className="progress">
                <div
                  className="progress__bar"
                  style={{ width: `${Math.round(s.progress * 100)}%` }}
                />
              </div>
              <div className="card__meta">
                <span>{eventLabel(s, snapshot.nodes, lang)}</span>
                <span className="muted">{fmtRelative(s.last_event_at, ref)}</span>
              </div>
              {holdLabel(s, snapshot.nodes, lang) && (
                <div className="hold">⚠ {holdLabel(s, snapshot.nodes, lang)}</div>
              )}
            </button>
          </li>
        ))}
      </ul>
    </>
  );
}
