import { afterEach, describe, expect, it, vi } from "vitest";
import { type BasemapPreset, isDarkBasemap, resolveStyle } from "./style";

const RASTER = { version: 8 as const, sources: {}, layers: [] };
const preset = (candidates: BasemapPreset["candidates"]): BasemapPreset => ({
  id: "dark",
  label: "t",
  hint: "",
  candidates,
});

type Handler = (url: string) => Promise<Partial<Response>>;
function stubFetch(handler: Handler) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => handler(url)),
  );
}
const okJson = async () => ({ ok: true, json: async () => ({ version: 8 }) });
const okHtml = async () => ({
  ok: true,
  json: async () => {
    throw new SyntaxError("not json");
  },
});

afterEach(() => vi.unstubAllGlobals());

describe("resolveStyle", () => {
  it("берёт первого ответившего векторного кандидата", async () => {
    stubFetch(async (url) =>
      url.includes("a.example") ? Promise.reject(new Error("net")) : okJson(),
    );
    const r = await resolveStyle(
      preset(["https://a.example/style.json", "https://b.example/style.json", RASTER]),
    );
    expect(r).toEqual({ style: "https://b.example/style.json", fallback: false });
  });

  it("HTML-заглушка вместо style.json не считается ответом", async () => {
    stubFetch(okHtml);
    const r = await resolveStyle(preset(["https://a.example/style.json", RASTER]));
    expect(r).toEqual({ style: RASTER, fallback: true });
  });

  it("все векторные недоступны — растр с пометкой fallback", async () => {
    stubFetch(async () => ({ ok: false }));
    const r = await resolveStyle(
      preset(["https://a.example/style.json", "https://b.example/style.json", RASTER]),
    );
    expect(r.style).toBe(RASTER);
    expect(r.fallback).toBe(true);
  });

  it("пресет только из растра не ходит в сеть", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const r = await resolveStyle(preset([RASTER]));
    expect(r).toEqual({ style: RASTER, fallback: false });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("isDarkBasemap", () => {
  it("тёмные — dark, satellite, custom", () => {
    expect(isDarkBasemap("dark")).toBe(true);
    expect(isDarkBasemap("satellite")).toBe(true);
    expect(isDarkBasemap("light")).toBe(false);
    expect(isDarkBasemap("detailed")).toBe(false);
  });
});
