/**
 * Подписи HTML-маркеров не налезают друг на друга.
 *
 * Symbol-слои MapLibre разводят подписи сами, но им нужен glyph-сервер; у нас
 * подписи — HTML-маркеры (см. CLAUDE.md), поэтому коллизии решаем здесь: жадно
 * по приоритету, как MapLibre. Подпись важнее — ставится первой; следующая,
 * если налезает на уже поставленную подпись или на точку более важного
 * маркера, пробует другую сторону от точки, а если и там тесно — прячется
 * (сам маркер остаётся, имя — в title по наведению).
 */

export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface LabelItem {
  id: string;
  priority: number;
  candidates: Box[]; // места подписи в порядке предпочтения (справа от точки, слева)
  anchor?: Box; // точка/иконка маркера — препятствие для менее важных подписей
}

export function overlaps(a: Box, b: Box, pad = 0): boolean {
  return (
    a.x < b.x + b.w + pad && b.x < a.x + a.w + pad && a.y < b.y + b.h + pad && b.y < a.y + a.h + pad
  );
}

/** Для каждой подписи — индекс выбранного места среди candidates или -1 (спрятать). */
export function declutter(items: readonly LabelItem[], pad = 2): Map<string, number> {
  const order = [...items].sort((a, b) => b.priority - a.priority || a.id.localeCompare(b.id));
  const placed: Box[] = [];
  const result = new Map<string, number>();
  for (const item of order) {
    // strict: не закрывать ничью точку; иначе — только точки менее важных маркеров
    const fits = (box: Box, strict: boolean) =>
      !placed.some((other) => overlaps(box, other, pad)) &&
      !items.some(
        (other) =>
          other.id !== item.id &&
          other.anchor !== undefined &&
          (strict || other.priority >= item.priority) &&
          overlaps(box, other.anchor),
      );
    let index = item.candidates.findIndex((box) => fits(box, true));
    if (index < 0) index = item.candidates.findIndex((box) => fits(box, false));
    result.set(item.id, index);
    if (index >= 0) placed.push(item.candidates[index]);
  }
  return result;
}

/** Приоритеты: выбранный груз > порты с риском > порты > грузы > паромы > ж/д узлы. */
export const LABEL_PRIORITY = {
  selectedCargo: 100,
  portCritical: 90,
  portWarning: 85,
  portWatch: 80,
  port: 75,
  delayedCargo: 60,
  cargo: 55,
  vessel: 45,
  node: 40,
  deliveredCargo: 30,
} as const;
