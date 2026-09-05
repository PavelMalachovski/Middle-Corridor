import { createContext, type ReactNode, useCallback, useContext, useMemo, useState } from "react";
import { en } from "./en";
import { type Key, ru } from "./ru";

/**
 * Два словаря и функция подстановки — без библиотеки. Язык живёт в модуле
 * (для форматтеров вне React) и в контексте (чтобы дерево перерисовалось).
 * Выбор запоминается в localStorage, по умолчанию — из языка браузера.
 */

export type Lang = "ru" | "en";
export type { Key };

const STORAGE_KEY = "mc-lang";
const DICTS: Record<Lang, Record<Key, string>> = { ru, en };

function detect(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "ru" || saved === "en") return saved;
  } catch {
    /* приватный режим */
  }
  if (typeof navigator !== "undefined" && /^en\b/i.test(navigator.language ?? "")) return "en";
  return "ru";
}

let current: Lang = typeof window === "undefined" ? "ru" : detect();

export function getLang(): Lang {
  return current;
}

/** Только для тестов и провайдера: меняет язык форматтеров вне React. */
export function setLangGlobal(lang: Lang): void {
  current = lang;
  if (typeof document !== "undefined") document.documentElement.lang = lang;
  try {
    localStorage.setItem(STORAGE_KEY, lang);
  } catch {
    /* ignore */
  }
}

export type Params = Record<string, string | number>;

export function translate(lang: Lang, key: Key, params?: Params): string {
  let text = DICTS[lang][key] ?? DICTS.ru[key] ?? key;
  if (params) {
    for (const [k, v] of Object.entries(params)) text = text.replaceAll(`{${k}}`, String(v));
  }
  return text;
}

/** Текущий язык модуля — для кода вне React (форматтеры, маркеры карты). */
export function t(key: Key, params?: Params): string {
  return translate(current, key, params);
}

interface I18n {
  lang: Lang;
  t: (key: Key, params?: Params) => string;
  setLang: (lang: Lang) => void;
}

const I18nContext = createContext<I18n>({ lang: current, t, setLang: setLangGlobal });

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(current);
  const setLang = useCallback((next: Lang) => {
    setLangGlobal(next);
    setLangState(next);
  }, []);
  const value = useMemo<I18n>(
    () => ({ lang, t: (key, params) => translate(lang, key, params), setLang }),
    [lang, setLang],
  );
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18n {
  return useContext(I18nContext);
}

// --- названия из данных ---------------------------------------------------------------

interface Named {
  name: string;
  name_en?: string | null;
}

/** Название узла на текущем языке; без английского — русское. */
export function nodeName(node: Named | null | undefined, lang: Lang = current): string {
  if (!node) return "";
  return lang === "en" && node.name_en ? node.name_en : node.name;
}

export function nodeNameByCode(
  nodes: (Named & { code: string })[],
  code: string | null | undefined,
  lang: Lang = current,
): string {
  if (!code) return "";
  const node = nodes.find((n) => n.code === code);
  return node ? nodeName(node, lang) : code;
}
