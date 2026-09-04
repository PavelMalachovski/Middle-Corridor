/**
 * Геометрия мобильной шторки: три положения и правило, куда прилипнуть
 * после перетаскивания. Чистые функции — проверяются без DOM.
 */

export type SheetState = "peek" | "half" | "full";

export const SHEET_VH: Record<SheetState, number> = { peek: 0, half: 0.45, full: 0.88 };
export const HEADER_PX = 64; // ручка + вкладки — столько остаётся видно в peek
export const FLICK_PX_PER_MS = 0.4; // быстрее — это флик, а не перетаскивание
export const SHEET_ORDER: SheetState[] = ["full", "half", "peek"]; // сверху вниз

export const clamp = (v: number, lo: number, hi: number): number => Math.min(Math.max(v, lo), hi);

export const fullHeight = (innerHeight: number): number => innerHeight * SHEET_VH.full;

/** Сколько пикселей шторки видно в данном положении. */
export const visibleFor = (s: SheetState, innerHeight: number): number =>
  s === "peek" ? HEADER_PX : innerHeight * SHEET_VH[s];

/** translateY шторки: 0 — полностью выдвинута, больше — ниже. */
export const offsetFor = (s: SheetState, innerHeight: number): number =>
  fullHeight(innerHeight) - visibleFor(s, innerHeight);

export const maxOffset = (innerHeight: number): number => fullHeight(innerHeight) - HEADER_PX;

/**
 * Куда прилипнуть после отпускания: быстрый флик листает на одно положение
 * в сторону движения, медленное перетаскивание — к ближайшему положению.
 */
export function snapSheet(
  current: SheetState,
  offset: number,
  velocityPxPerMs: number,
  innerHeight: number,
): SheetState {
  const idx = SHEET_ORDER.indexOf(current);
  if (velocityPxPerMs > FLICK_PX_PER_MS)
    return SHEET_ORDER[Math.min(idx + 1, SHEET_ORDER.length - 1)];
  if (velocityPxPerMs < -FLICK_PX_PER_MS) return SHEET_ORDER[Math.max(idx - 1, 0)];
  return SHEET_ORDER.reduce((best, s) =>
    Math.abs(offsetFor(s, innerHeight) - offset) < Math.abs(offsetFor(best, innerHeight) - offset)
      ? s
      : best,
  );
}
