import { describe, expect, it } from "vitest";
import type { NodeStatus, Shipment } from "./api";
import {
  EMPTY_FILTER,
  filterShipments,
  isFilterActive,
  matchesQuery,
  matchesStatus,
} from "./shipmentFilter";

const ship = (over: Partial<Shipment> & { from?: string }): Shipment =>
  ({
    ref: "MC-26-0001",
    client: "Tianshan Trade",
    cargo: "станки",
    origin: "Сиань",
    destination: "Будапешт",
    state: "in_transit",
    delay_hours: 0,
    position: { from_code: over.from ?? "AKTAU", to_code: null },
    ...over,
  }) as unknown as Shipment;
const nodes = [
  { code: "AKTAU", leg: "caspian" },
  { code: "ALMATY", leg: "rail_cis" },
] as unknown as NodeStatus[];

describe("matchesQuery", () => {
  it("по номеру, клиенту, грузу и городам, без учёта регистра", () => {
    const s = ship({});
    expect(matchesQuery(s, "0001")).toBe(true);
    expect(matchesQuery(s, "tianshan")).toBe(true);
    expect(matchesQuery(s, "СТАНКИ")).toBe(true);
    expect(matchesQuery(s, "будап")).toBe(true);
    expect(matchesQuery(s, "  ")).toBe(true);
    expect(matchesQuery(s, "поти")).toBe(false);
  });
});

describe("matchesStatus", () => {
  it("активные, с задержкой, точные состояния", () => {
    expect(matchesStatus(ship({ state: "delivered" }), "active")).toBe(false);
    expect(matchesStatus(ship({ state: "waiting" }), "active")).toBe(true);
    expect(matchesStatus(ship({ delay_hours: 3 }), "delayed")).toBe(true);
    expect(matchesStatus(ship({ delay_hours: 3, state: "delivered" }), "delayed")).toBe(false);
    expect(matchesStatus(ship({ state: "waiting" }), "waiting")).toBe(true);
    expect(matchesStatus(ship({ state: "waiting" }), "in_transit")).toBe(false);
  });
});

describe("filterShipments", () => {
  const list = [
    ship({ ref: "MC-26-0001", from: "AKTAU" }),
    ship({ ref: "MC-26-0002", from: "ALMATY", delay_hours: 5 }),
    ship({ ref: "MC-26-0003", from: "AKTAU", state: "delivered" }),
  ];
  it("комбинирует поиск, статус и плечо", () => {
    expect(filterShipments(list, EMPTY_FILTER, nodes).map((s) => s.ref)).toEqual([
      "MC-26-0001",
      "MC-26-0002",
      "MC-26-0003",
    ]);
    expect(
      filterShipments(list, { ...EMPTY_FILTER, leg: "caspian" }, nodes).map((s) => s.ref),
    ).toEqual(["MC-26-0001", "MC-26-0003"]);
    expect(
      filterShipments(list, { ...EMPTY_FILTER, status: "delayed" }, nodes).map((s) => s.ref),
    ).toEqual(["MC-26-0002"]);
    expect(
      filterShipments(list, { query: "0003", status: "delivered", leg: "caspian" }, nodes).map(
        (s) => s.ref,
      ),
    ).toEqual(["MC-26-0003"]);
  });
  it("isFilterActive", () => {
    expect(isFilterActive(EMPTY_FILTER)).toBe(false);
    expect(isFilterActive({ ...EMPTY_FILTER, query: " x" })).toBe(true);
    expect(isFilterActive({ ...EMPTY_FILTER, leg: "europe" })).toBe(true);
  });
});
