import { describe, expect, it } from "vitest";
import { buildSearch, formatView, parseUrlState, parseView, sameSearch } from "./urlState";

describe("parseView / formatView", () => {
  it("zoom/lat/lon с округлением", () => {
    expect(parseView("5.5/43.6/51.2")).toEqual({ zoom: 5.5, lat: 43.6, lon: 51.2 });
    expect(formatView({ zoom: 5.5049, lat: 43.60004, lon: 51.2 })).toBe("5.5/43.6/51.2");
  });
  it("мусор — null", () => {
    expect(parseView(null)).toBeNull();
    expect(parseView("5/43")).toBeNull();
    expect(parseView("x/1/2")).toBeNull();
    expect(parseView("30/43/51")).toBeNull();
    expect(parseView("5/95/51")).toBeNull();
  });
});

describe("parseUrlState", () => {
  it("полная ссылка", () => {
    const st = parseUrlState(
      "?s=mc-26-0412&view=6/43.5/50.5&basemap=light&at=2026-09-05T12:00:00Z",
    );
    expect(st.s).toBe("MC-26-0412");
    expect(st.view).toEqual({ zoom: 6, lat: 43.5, lon: 50.5 });
    expect(st.basemap).toBe("light");
    expect(st.at?.toISOString()).toBe("2026-09-05T12:00:00.000Z");
  });
  it("пусто и невалидные значения", () => {
    const st = parseUrlState("");
    expect(st).toEqual({ s: null, view: null, basemap: null, at: null });
    const bad = parseUrlState("basemap=neon&at=yesterday&s=%20");
    expect(bad.basemap).toBeNull();
    expect(bad.at).toBeNull();
    expect(bad.s).toBeNull();
  });
});

describe("buildSearch", () => {
  it("умолчания не пишутся, порядок стабилен", () => {
    expect(buildSearch({})).toBe("");
    expect(buildSearch({ basemap: "dark" })).toBe("");
    expect(
      buildSearch({
        s: "MC-26-0412",
        view: { zoom: 6, lat: 43.5, lon: 50.5 },
        basemap: "light",
        at: new Date("2026-09-05T12:00:00.000Z"),
      }),
    ).toBe("s=MC-26-0412&view=6/43.5/50.5&basemap=light&at=2026-09-05T12:00:00Z");
  });
  it("круг: parse(build(x)) == x", () => {
    const x = {
      s: "MC-26-0351",
      view: { zoom: 4.25, lat: 41.1234, lon: 49.5 },
      basemap: "satellite" as const,
      at: null,
    };
    expect(parseUrlState(buildSearch(x))).toEqual(x);
  });
  it("sameSearch не зависит от ведущего ?", () => {
    expect(sameSearch("?a=1", "a=1")).toBe(true);
    expect(sameSearch("a=1", "a=2")).toBe(false);
  });
});
