/// <reference types="node" />
// Файл читаем с диска: `?raw` для CSS в Vitest отдаёт пустую строку (CSS не обрабатывается)
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const source = readFileSync(new URL("./styles.css", import.meta.url), "utf8");

/**
 * Сторож дизайн-токенов: цвет задаётся только в блоках токенов (:root, светлая
 * тема, подложка), правила берут var(--…). Иначе светлая тема расползается:
 * захардкоженный #fff на белой панели не виден, и никто не заметит.
 */
const css = source.replace(/\/\*[\s\S]*?\*\//g, "");
const LITERAL = /#[0-9a-fA-F]{3,8}\b|rgba?\(\s*\d/;

/** Самые внутренние блоки «селектор { объявления }». */
function blocks(source: string): { selector: string; body: string }[] {
  return [...source.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => ({
    selector: m[1].trim(),
    body: m[2],
  }));
}

describe("styles.css: цвета только через токены", () => {
  it("вне блоков токенов нет hex и rgb()-литералов", () => {
    const offenders = blocks(css)
      .filter(({ body }) => {
        const decls = body
          .split(";")
          .map((d) => d.trim())
          .filter(Boolean);
        const tokenBlock = decls.every((d) => d.startsWith("--") || !d.includes(":"));
        return !tokenBlock && decls.some((d) => !d.startsWith("--") && LITERAL.test(d));
      })
      .map(({ selector }) => selector.split("\n").pop());
    expect(offenders).toEqual([]);
  });

  it("светлая тема переопределяет все токены текста и поверхностей", () => {
    const light = blocks(css).find((b) => b.selector.includes('[data-theme="light"]'));
    expect(light).toBeDefined();
    for (const token of ["--bg", "--panel", "--text", "--muted", "--ink", "--accent-text"]) {
      expect(light?.body).toContain(`${token}:`);
    }
  });
});
