import { useCallback, useEffect, useRef, useState } from "react";
import type { Snapshot } from "./api";

/**
 * Шкала времени: replayAt — момент, на который запрашивается снимок
 * (null = живой режим). Воспроизведение двигает replayAt со скоростью
 * speed × реальное время. Окно ±N часов задаёт бэкенд (snapshot.live).
 *
 * «Сейчас» считаем по серверным часам: server_time последнего снимка плюс
 * прошедшее с его получения время. В моке с ускоренным временем это
 * расходится с часами клиента — поэтому опора обновляется каждым снимком.
 */

export const SPEEDS = [60, 600, 3600] as const;
export type Speed = (typeof SPEEDS)[number];

const H = 3_600_000;
const TICK_MS = 400;
const EDGE_MARGIN_MS = 15 * 60_000; // не подходить к краю окна вплотную: сервер отдаст 400
const PLAY_FROM_LIVE_H = 24; // «play» из живого режима — сутки назад

export interface ReplayWindow {
  pastHours: number;
  futureHours: number;
}

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

const DEFAULT_WINDOW: ReplayWindow = { pastHours: 72, futureHours: 24 };

export function useReplay(): ReplayControl {
  const [replayAt, setReplayAt] = useState<Date | null>(null);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<Speed>(600);
  const replayRef = useRef<Date | null>(null);
  replayRef.current = replayAt;

  const clock = useRef({ serverMs: Date.now(), wallMs: Date.now() });
  const windowRef = useRef<ReplayWindow>(DEFAULT_WINDOW);
  /** Каждый полученный снимок подстраивает серверные часы и окно replay. */
  const sync = useCallback((snapshot: Snapshot | null, fetchedAt: Date | null) => {
    if (!snapshot || !fetchedAt) return;
    const serverMs = Date.parse(snapshot.server_time);
    if (!Number.isNaN(serverMs)) clock.current = { serverMs, wallMs: fetchedAt.getTime() };
    windowRef.current = {
      pastHours: snapshot.live.replay_past_hours,
      futureHours: snapshot.live.replay_future_hours,
    };
  }, []);
  const serverNow = useCallback(
    () => clock.current.serverMs + (Date.now() - clock.current.wallMs),
    [],
  );

  const clamp = useCallback(
    (ms: number) => {
      const now = serverNow();
      const lo = now - windowRef.current.pastHours * H + EDGE_MARGIN_MS;
      const hi = now + windowRef.current.futureHours * H - EDGE_MARGIN_MS;
      return Math.min(Math.max(ms, lo), hi);
    },
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
      else scrub(new Date(serverNow() + hours * H));
    },
    [scrub, serverNow],
  );
  const goLive = useCallback(() => scrub(null), [scrub]);

  const togglePlay = useCallback(() => {
    setPlaying((p) => {
      if (!p && !replayRef.current) {
        setReplayAt(new Date(clamp(serverNow() - PLAY_FROM_LIVE_H * H)));
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
      const base = replayRef.current?.getTime() ?? serverNow() - PLAY_FROM_LIVE_H * H;
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

  const offsetHours = replayAt ? (replayAt.getTime() - serverNow()) / H : 0;

  return {
    replayAt,
    playing,
    speed,
    window: windowRef.current,
    serverNow,
    sync,
    offsetHours,
    scrub,
    scrubHours,
    goLive,
    togglePlay,
    setSpeed,
  };
}
