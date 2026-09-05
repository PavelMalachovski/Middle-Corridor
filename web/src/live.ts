import { useCallback, useEffect, useRef, useState } from "react";
import { fetchSnapshot, fetchWind, type Snapshot, streamUrl, type WindField } from "./api";

/**
 * Живые данные карты.
 *
 * - live-режим: если бэкенд умеет SSE (snapshot.live.stream), держим
 *   EventSource и получаем снимок каждые refresh_s; при трёх ошибках подряд
 *   переходим на поллинг. Иначе поллинг с интервалом refresh_s.
 * - replay-режим (replayAt задан): поток закрыт, снимок и ветер запрашиваются
 *   на момент replayAt с дебаунсом — шкалу времени можно тянуть свободно.
 */

export type LiveMode = "stream" | "poll" | "replay";

export interface LiveData {
  snapshot: Snapshot | null;
  wind: WindField | null;
  windAvailable: boolean;
  error: string | null;
  fetchedAt: Date | null;
  mode: LiveMode;
}

const WIND_POLL_MS = 60_000;
const WIND_STEP_DEG = 0.5; // поле только над морями — можно мельче: частицам виднее
const SCRUB_DEBOUNCE_MS = 120;
const WIND_SCRUB_MIN_MS = 1500; // поле ветра тяжёлое: в replay не чаще раза в полторы секунды
const STREAM_FAILURES_BEFORE_POLL = 3;

export function useLiveData(replayAt: Date | null): LiveData {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [wind, setWind] = useState<WindField | null>(null);
  const [windAvailable, setWindAvailable] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fetchedAt, setFetchedAt] = useState<Date | null>(null);
  const [mode, setMode] = useState<LiveMode>("poll");
  const streamBroken = useRef(false); // SSE не поднялся — до перезагрузки только поллинг
  const windFetchedAt = useRef(0);

  const applySnapshot = useCallback((data: Snapshot) => {
    setSnapshot(data);
    setFetchedAt(new Date());
    setError(null);
  }, []);

  const loadWind = useCallback(async (at: Date | null) => {
    try {
      const data = await fetchWind(at, WIND_STEP_DEG);
      setWind(data);
      setWindAvailable(data !== null);
    } catch {
      /* ветер — вспомогательный слой, ошибку не показываем */
    }
  }, []);

  // --- replay: снимок и ветер на момент replayAt --------------------------------
  useEffect(() => {
    if (!replayAt) return;
    setMode("replay");
    let alive = true;
    const t1 = setTimeout(async () => {
      try {
        const data = await fetchSnapshot(replayAt);
        if (alive) applySnapshot(data);
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      }
    }, SCRUB_DEBOUNCE_MS);
    // троттлинг с хвостом: при воспроизведении replayAt меняется каждые ~400 мс,
    // дебаунс никогда бы не сработал — а так ветер обновляется раз в WIND_SCRUB_MIN_MS
    const wait = Math.max(0, WIND_SCRUB_MIN_MS - (Date.now() - windFetchedAt.current));
    const t2 = setTimeout(() => {
      if (!alive) return;
      windFetchedAt.current = Date.now();
      void loadWind(replayAt);
    }, wait);
    return () => {
      alive = false;
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, [replayAt, applySnapshot, loadWind]);

  // --- live: поток или поллинг ----------------------------------------------------
  useEffect(() => {
    if (replayAt) return;
    let alive = true;
    let source: EventSource | null = null;
    let pollTimer: ReturnType<typeof setTimeout> | null = null;
    let failures = 0;

    const schedulePoll = (seconds: number) => {
      if (!alive) return;
      pollTimer = setTimeout(() => void poll(), seconds * 1000);
    };

    const poll = async () => {
      if (!alive) return;
      if (document.visibilityState !== "visible") {
        schedulePoll(2);
        return;
      }
      try {
        const data = await fetchSnapshot(null);
        if (!alive) return;
        applySnapshot(data);
        setMode("poll");
        schedulePoll(data.live.refresh_s);
      } catch (e) {
        if (!alive) return;
        setError(e instanceof Error ? e.message : String(e));
        schedulePoll(5);
      }
    };

    const openStream = (refreshS: number) => {
      if (typeof EventSource === "undefined") {
        schedulePoll(refreshS);
        return;
      }
      source = new EventSource(streamUrl());
      source.addEventListener("snapshot", (ev) => {
        failures = 0;
        applySnapshot(JSON.parse((ev as MessageEvent).data) as Snapshot);
        setMode("stream");
      });
      source.addEventListener("error", (ev) => {
        // серверное событие error несёт detail; сетевой обрыв — без данных
        const detail = (ev as MessageEvent).data as string | undefined;
        if (detail) {
          try {
            setError(`/api/v1/stream: ${(JSON.parse(detail) as { detail: string }).detail}`);
          } catch {
            setError("/api/v1/stream: ошибка источника");
          }
          return;
        }
        failures += 1;
        if (failures >= STREAM_FAILURES_BEFORE_POLL) {
          source?.close();
          source = null;
          streamBroken.current = true;
          schedulePoll(1);
        }
      });
    };

    const start = async () => {
      try {
        const data = await fetchSnapshot(null);
        if (!alive) return;
        applySnapshot(data);
        if (data.live.stream && !streamBroken.current) openStream(data.live.refresh_s);
        else {
          setMode("poll");
          schedulePoll(data.live.refresh_s);
        }
      } catch (e) {
        if (!alive) return;
        setError(e instanceof Error ? e.message : String(e));
        schedulePoll(5);
      }
    };

    void start();
    void loadWind(null);
    const windTimer = setInterval(() => {
      if (document.visibilityState === "visible") void loadWind(null);
    }, WIND_POLL_MS);

    return () => {
      alive = false;
      source?.close();
      if (pollTimer) clearTimeout(pollTimer);
      clearInterval(windTimer);
    };
  }, [replayAt, applySnapshot, loadWind]);

  return { snapshot, wind, windAvailable, error, fetchedAt, mode };
}
