import { useCallback, useEffect, useRef, useState } from "react";
import type { Snapshot } from "./api";
import {
  clampToWindow,
  estimateServerNow,
  HOUR_MS,
  offsetHours,
  type ReplayWindow,
  type ServerClock,
} from "./replayClock";

/**
 * Шкала времени: replayAt — момент, на который запрашивается снимок
 * (null = живой режим). Воспроизведение двигает replayAt со скоростью
 * speed × реальное время. Окно ±N часов задаёт бэкенд (snapshot.live).
 *
 * «Сейчас» считаем по серверным часам: server_time последнего снимка плюс
 * прошедшее с его получения время. В моке с ускоренным временем это
 * расходится с часами клиента — поэтому опора обновляется каждым снимком.
 * Арифметика — в replayClock.ts (чистые функции под юнит-тесты).
 */

export const SPEEDS = [60, 600, 3600] as const;
export type Speed = (typeof SPEEDS)[number];

const TICK_MS = 400;
const PLAY_FROM_LIVE_H = 24; // «play» из живого режима — сутки назад
const DEFAULT_WINDOW: ReplayWindow = { pastHours: 72, futureHours: 24 };

export type { ReplayWindow } from "./replayClock";

export interface ReplayControl {
  replayAt: Date | null;
  playing: boolean;
  speed: Speed;
  window: ReplayWindow;
  serverNow: () => number;
  sync: (snapshot: Snapshot | null, fetchedAt: Date | null) => void;
  /** Смещение шкалы в часах относительно «сейчас» (0 в живом режиме). */
  offsetHours: number;
  scrub: (at: Date | null) => void;
  scrubHours: (hours: number) => void;
  goLive: () => void;
  togglePlay: () => void;
  setSpeed: (s: Speed) => void;
}

export function useReplay(): ReplayControl {
  const [replayAt, setReplayAt] = useState<Date | null>(null);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<Speed>(600);
  const replayRef = useRef<Date | null>(null);
  replayRef.current = replayAt;

  const clock = useRef<ServerClock>({ serverMs: Date.now(), wallMs: Date.now() });
  const windowRef = useRef<ReplayWindow>(DEFAULT_WINDOW);
  /** Каждый полученный снимок подстраивает серверные часы и окно replay. */
  const sync = useCallback((snapshot: Snapshot | null, fetchedAt: Date | null) => {
    if (!snapshot || !fetchedAt) return;
    const serverMs = Date.parse(snapshot.server_time);
    if (!Number.isNaN(serverMs)) {
      clock.current = {
        serverMs,
        wallMs: fetchedAt.getTime(),
        scale: snapshot.live.time_scale ?? 1,
      };
    }
    windowRef.current = {
      pastHours: snapshot.live.replay_past_hours,
      futureHours: snapshot.live.replay_future_hours,
    };
  }, []);
  const serverNow = useCallback(() => estimateServerNow(clock.current), []);
  const clamp = useCallback(
    (ms: number) => clampToWindow(ms, serverNow(), windowRef.current),
    [serverNow],
  );

  const scrub = useCallback(
    (at: Date | null) => {
      if (!at) {
        setReplayAt(null);
        setPlaying(false);
        return;
      }
      setReplayAt(new Date(clamp(at.getTime())));
    },
    [clamp],
  );
  const scrubHours = useCallback(
    (hours: number) => {
      if (Math.abs(hours) < 0.01) scrub(null);
      else scrub(new Date(serverNow() + hours * HOUR_MS));
    },
    [scrub, serverNow],
  );
  const goLive = useCallback(() => scrub(null), [scrub]);

  const togglePlay = useCallback(() => {
    setPlaying((p) => {
      if (!p && !replayRef.current) {
        setReplayAt(new Date(clamp(serverNow() - PLAY_FROM_LIVE_H * HOUR_MS)));
      }
      return !p;
    });
  }, [clamp, serverNow]);

  // --- воспроизведение --------------------------------------------------------------
  useEffect(() => {
    if (!playing) return;
    let last = performance.now();
    const timer = setInterval(() => {
      const now = performance.now();
      const dt = now - last;
      last = now;
      const base = replayRef.current?.getTime() ?? serverNow() - PLAY_FROM_LIVE_H * HOUR_MS;
      const next = base + dt * speed;
      const end = clamp(Number.POSITIVE_INFINITY);
      if (next >= end) {
        setReplayAt(new Date(end));
        setPlaying(false);
      } else {
        setReplayAt(new Date(next));
      }
    }, TICK_MS);
    return () => clearInterval(timer);
  }, [playing, speed, clamp, serverNow]);

  return {
    replayAt,
    playing,
    speed,
    window: windowRef.current,
    serverNow,
    sync,
    offsetHours: replayAt ? offsetHours(replayAt.getTime(), serverNow()) : 0,
    scrub,
    scrubHours,
    goLive,
    togglePlay,
    setSpeed,
  };
}
