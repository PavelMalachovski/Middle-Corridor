import { describe, expect, it } from "vitest";
import { en } from "./en";
import { nodeName, translate } from "./index";
import { ru } from "./ru";

describe("словари", () => {
  it("английский покрывает все ключи русского, лишних нет", () => {
    const ruKeys = Object.keys(ru).sort();
    const enKeys = Object.keys(en).sort();
    expect(enKeys).toEqual(ruKeys);
  });
  it("подстановки совпадают по ключам", () => {
    for (const key of Object.keys(ru) as (keyof typeof ru)[]) {
      const p = (s: string) => (s.match(/\{[a-z]+\}/g) ?? []).sort();
      expect(p(en[key]), key).toEqual(p(ru[key]));
    }
  });
  it("нет пустых строк", () => {
    for (const d of [ru, en])
      for (const [k, v] of Object.entries(d)) expect(v.trim(), k).not.toBe("");
  });
});

describe("translate / nodeName", () => {
  it("подставляет параметры на обоих языках", () => {
    expect(translate("ru", "card.delivered", { node: "Поти" })).toBe("Доставлен: Поти");
    expect(translate("en", "card.delivered", { node: "Poti" })).toBe("Delivered: Poti");
    expect(translate("en", "top.updated", { sec: 3, mode: "stream" })).toBe(
      "updated 3 s ago · stream",
    );
  });
  it("название узла: английское при наличии, иначе русское", () => {
    const n = { name: "Баку (Алят)", name_en: "Baku (Alat)" };
    expect(nodeName(n, "ru")).toBe("Баку (Алят)");
    expect(nodeName(n, "en")).toBe("Baku (Alat)");
    expect(nodeName({ name: "Поти", name_en: null }, "en")).toBe("Поти");
  });
});
