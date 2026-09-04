import { useEffect } from "react";
import { fmtTs } from "../format";
import { SPEEDS, type ReplayControl } from "../replay";

interface Props {
  replay: ReplayControl;
  disabled: boolean; // нет снимка — шкала не активна
}

const STEP_H = 0.25;

function fmtOffset(hours: number): string {
  const abs = Math.abs(hours);
  const sign = hours < 0 ? "−" : "+";
  if (abs < 1) return `${sign}${Math.round(abs * 60)} мин`;
  if (abs < 48) return `${sign}${abs < 10 ? abs.toFixed(1).replace(".0", "") : Math.round(abs)} ч`;
  return `${sign}${(abs / 24).toFixed(1).replace(".0", "")} дн`;
}

export function Timeline({ replay, disabled }: Props) {
  const { replayAt, playing, speed, window: win, offsetHours } = replay;
  const live = replayAt === null;
  const span = win.pastHours + win.futureHours;
  const nowPct = (win.pastHours / span) * 100;
  const posPct = ((offsetHours + win.pastHours) / span) * 100;

  // пробел — play/pause, когда фокус не в поле ввода
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (e.code !== "Space" || disabled) return;
      if (t && (t.tagName === "INPUT" || t.tagName === "BUTTON" || t.tagName === "TEXTAREA")) return;
      e.preventDefault();
      replay.togglePlay();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [replay, disabled]);

  const ticks: number[] = [];
  for (let h = -win.pastHours; h <= win.futureHours; h += 24) ticks.push(h);

  return (
    <div className={`timeline ${live ? "timeline--live" : "timeline--replay"} ${playing ? "is-playing" : ""}`}>
      <div className="timeline__controls">
        <button
          type="button"
          className="timeline__play"
          onClick={replay.togglePlay}
          disabled={disabled}
          title={playing ? "Пауза (пробел)" : live ? "Воспроизвести последние сутки (пробел)" : "Воспроизвести (пробел)"}
          aria-label={playing ? "Пауза" : "Воспроизвести"}
        >
          {playing ? "❚❚" : "▶"}
        </button>
        <div className="timeline__speeds" role="group" aria-label="Скорость">
          {SPEEDS.map((s) => (
            <button
              key={s}
              type="button"
              className={`timeline__speed ${speed === s ? "is-on" : ""}`}
              onClick={() => replay.setSpeed(s)}
              disabled={disabled}
              title={`×${s}: ${s === 60 ? "минута = час" : s === 600 ? "минута = 10 часов" : "секунда = час"}`}
            >
              ×{s}
            </button>
          ))}
        </div>
      </div>

      <div className="timeline__track-wrap">
        <div className="timeline__track" aria-hidden="true">
          <div className="timeline__past" style={{ width: `${nowPct}%` }} />
          <div className="timeline__future" style={{ left: `${nowPct}%` }} />
          <div className="timeline__fill" style={{ left: `${Math.min(nowPct, posPct)}%`, width: `${Math.abs(posPct - nowPct)}%` }} />
          <div className="timeline__now" style={{ left: `${nowPct}%` }} />
          {ticks.map((h, i) => (
            <div
              key={h}
              className={`timeline__tick ${i === 0 ? "timeline__tick--first" : i === ticks.length - 1 ? "timeline__tick--last" : ""}`}
              style={{ left: `${((h + win.pastHours) / span) * 100}%` }}
            >
              <span>{h === 0 ? "сейчас" : h > 0 ? `+${h} ч` : `${h} ч`}</span>
            </div>
          ))}
        </div>
        <input
          type="range"
          className="timeline__range"
          min={-win.pastHours}
          max={win.futureHours}
          step={STEP_H}
          value={Math.round(offsetHours / STEP_H) * STEP_H}
          disabled={disabled}
          onChange={(e) => replay.scrubHours(Number(e.target.value))}
          aria-label="Момент времени"
          aria-valuetext={live ? "сейчас" : `${fmtTs(replayAt.toISOString())}, ${fmtOffset(offsetHours)}`}
        />
      </div>

      <div className="timeline__readout">
        {live ? (
          <span className="timeline__time">
            <i className="dot-live" /> сейчас
          </span>
        ) : (
          <span className="timeline__time mono" title={fmtOffset(offsetHours)}>
            {fmtTs(replayAt.toISOString()).replace(" UTC", "")}
            <b className={offsetHours > 0 ? "timeline__offset timeline__offset--future" : "timeline__offset"}>
              {fmtOffset(offsetHours)}
            </b>
          </span>
        )}
        <button
          type="button"
          className={`chip timeline__live ${live ? "chip--on" : ""}`}
          onClick={replay.goLive}
          disabled={disabled || live}
          title="Вернуться к живым данным"
        >
          LIVE
        </button>
      </div>
    </div>
  );
}
