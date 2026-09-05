import type { NodeStatus, Shipment } from "./api";

/** Поиск и фильтры списка грузов — чистые функции под юнит-тесты. */

export type StatusFilter = "all" | "active" | "in_transit" | "waiting" | "delayed" | "delivered";
export type LegFilter = "all" | "rail_cis" | "caspian" | "rail_caucasus" | "black_sea" | "europe";

export interface ShipmentFilter {
  query: string;
  status: StatusFilter;
  leg: LegFilter;
}

export const EMPTY_FILTER: ShipmentFilter = { query: "", status: "all", leg: "all" };

export const STATUS_OPTIONS: StatusFilter[] = [
  "all",
  "active",
  "in_transit",
  "waiting",
  "delayed",
  "delivered",
];

export const LEG_OPTIONS: LegFilter[] = [
  "all",
  "rail_cis",
  "caspian",
  "rail_caucasus",
  "black_sea",
  "europe",
];

/** Плечо, на котором груз сейчас: по узлу, откуда он движется (или где стоит). */
export function shipmentLeg(s: Shipment, nodes: NodeStatus[]): string | null {
  const code = s.position.from_code;
  return nodes.find((n) => n.code === code)?.leg ?? null;
}

export function matchesStatus(s: Shipment, status: StatusFilter): boolean {
  switch (status) {
    case "all":
      return true;
    case "active":
      return s.state !== "delivered";
    case "delayed":
      return s.delay_hours >= 1 && s.state !== "delivered";
    default:
      return s.state === status;
  }
}

export function matchesQuery(s: Shipment, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return [s.ref, s.client, s.cargo, s.origin, s.destination]
    .filter(Boolean)
    .some((v) => v.toLowerCase().includes(q));
}

export function filterShipments(
  shipments: Shipment[],
  filter: ShipmentFilter,
  nodes: NodeStatus[],
): Shipment[] {
  return shipments.filter(
    (s) =>
      matchesQuery(s, filter.query) &&
      matchesStatus(s, filter.status) &&
      (filter.leg === "all" || shipmentLeg(s, nodes) === filter.leg),
  );
}

export function isFilterActive(f: ShipmentFilter): boolean {
  return f.query.trim() !== "" || f.status !== "all" || f.leg !== "all";
}
