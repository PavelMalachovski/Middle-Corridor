import { useEffect } from "react";
import { fmtTs } from "../format";
import { type Key, useI18n } from "../i18n";
import { type ReplayControl, SPEEDS } from "../replay";
import { fmtOffset } from "../replayClock";

interface Props {
  replay: ReplayControl;
  disabled: boolean; // нет снимка — шкала не активна
}

const STEP_H = 0.25;

export function Timeline({ replay, disabled }: Props) {
  const { t } = useI18n();
  const { replayAt, playing, speed, window: win, offsetHours } = replay;
  const live = replayAt === null;
  const span = win.pastHours + win.futureHours;
  const nowPct = (win.pastHours / span) * 100;
  const posPct = ((offsetHours + win.pastHours) / span) * 100;

  // пробел — play/pause, когда фокус не в поле ввода
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (e.code !== "Space" || disabled) return;
      if (el && (el.tagName === "INPUT" || el.tagName === "BUTTON" || el.tagName === "TEXTAREA"))
        return;
      e.preventDefault();
      replay.togglePlay();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [replay, disabled]);

  const ticks: number[] = [];
  for (let h = -win.pastHours; h <= win.futureHours; h += 24) ticks.push(h);
  const hourUnit = t("common.h");

  return (
    <div
      className={`timeline ${live ? "timeline--live" : "timeline--replay"} ${playing ? "is-playing" : ""}`}
    >
      <div className="timeline__controls">
        <button
          type="button"
          className="timeline__play"
          onClick={replay.togglePlay}
          disabled={disabled}
          title={playing ? t("time.pause") : live ? t("time.playDay") : t("time.play")}
          aria-label={playing ? t("time.pauseAria") : t("time.playAria")}
        >
          {playing ? "❚❚" : "▶"}
        </button>
        <fieldset className="timeline__speeds">
          <legend className="sr-only">{t("time.speed")}</legend>
          {SPEEDS.map((s) => (
            <button
              key={s}
              type="button"
              className={`timeline__speed ${speed === s ? "is-on" : ""}`}
              onClick={() => replay.setSpeed(s)}
              disabled={disabled}
              title={`×${s}: ${t(`time.speed${s}` as Key)}`}
            >
              ×{s}
            </button>
          ))}
        </fieldset>
      </div>

      <div className="timeline__track-wrap">
        <div className="timeline__track" aria-hidden="true">
          <div className="timeline__past" style={{ width: `${nowPct}%` }} />
          <div className="timeline__future" style={{ left: `${nowPct}%` }} />
          <div
            className="timeline__fill"
            style={{ left: `${Math.min(nowPct, posPct)}%`, width: `${Math.abs(posPct - nowPct)}%` }}
          />
          <div className="timeline__now" style={{ left: `${nowPct}%` }} />
          {ticks.map((h, i) => (
            <div
              key={h}
              className={`timeline__tick ${i === 0 ? "timeline__tick--first" : i === ticks.length - 1 ? "timeline__tick--last" : ""}`}
              style={{ left: `${((h + win.pastHours) / span) * 100}%` }}
            >
              <span>
                {h === 0 ? t("common.now") : h > 0 ? `+${h} ${hourUnit}` : `${h} ${hourUnit}`}
              </span>
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
          aria-label={t("time.moment")}
          aria-valuetext={
            live ? t("common.now") : `${fmtTs(replayAt.toISOString())}, ${fmtOffset(offsetHours)}`
          }
        />
      </div>

      <div className="timeline__readout">
        {live ? (
          <span className="timeline__time">
            <i className="dot-live" /> {t("common.now")}
          </span>
        ) : (
          <span className="timeline__time mono" title={fmtOffset(offsetHours)}>
            {fmtTs(replayAt.toISOString()).replace(" UTC", "")}
            <b
              className={
                offsetHours > 0 ? "timeline__offset timeline__offset--future" : "timeline__offset"
              }
            >
              {fmtOffset(offsetHours)}
            </b>
          </span>
        )}
        <button
          type="button"
          className={`chip timeline__live ${live ? "chip--on" : ""}`}
          onClick={replay.goLive}
          disabled={disabled || live}
          title={t("time.live")}
        >
          LIVE
        </button>
      </div>
    </div>
  );
}
