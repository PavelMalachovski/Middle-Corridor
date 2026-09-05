/**
 * Чистая арифметика шкалы времени: серверные часы, окно replay, подписи.
 * Вынесена из хука useReplay, чтобы проверяться юнит-тестами без React.
 */

export const HOUR_MS = 3_600_000;
export const EDGE_MARGIN_MS = 15 * 60_000; // не подходить к краю окна вплотную: сервер отдаст 400

export interface ReplayWindow {
  pastHours: number;
  futureHours: number;
}

/** Опорная пара «серверное время ↔ время клиента» на момент получения снимка. */
export interface ServerClock {
  serverMs: number;
  wallMs: number;
  /** Во сколько раз серверные часы быстрее настенных (мок с MOCK_TIME_SCALE); 1 — обычно. */
  scale?: number;
}

/** Серверное «сейчас»: опора плюс прошедшее у клиента время (умноженное на скорость часов). */
export function estimateServerNow(clock: ServerClock, wallNow: number = Date.now()): number {
  return clock.serverMs + (wallNow - clock.wallMs) * (clock.scale ?? 1);
}

/** Момент внутри окна [now − past, now + future] с отступом от краёв. */
export function clampToWindow(
  ms: number,
  nowMs: number,
  win: ReplayWindow,
  marginMs: number = EDGE_MARGIN_MS,
): number {
  const lo = nowMs - win.pastHours * HOUR_MS + marginMs;
  const hi = nowMs + win.futureHours * HOUR_MS - marginMs;
  return Math.min(Math.max(ms, lo), hi);
}

export function offsetHours(replayMs: number, nowMs: number): number {
  return (replayMs - nowMs) / HOUR_MS;
}

/** «−30 мин», «−6 ч», «+1.5 дн» — смещение относительно «сейчас». */
export function fmtOffset(hours: number): string {
  const abs = Math.abs(hours);
  const sign = hours < 0 ? "−" : "+";
  if (abs < 1) return `${sign}${Math.round(abs * 60)} мин`;
  if (abs < 48) return `${sign}${abs < 10 ? abs.toFixed(1).replace(".0", "") : Math.round(abs)} ч`;
  return `${sign}${(abs / 24).toFixed(1).replace(".0", "")} дн`;
}
