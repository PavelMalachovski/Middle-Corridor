import type { Thresholds, WindHour } from "../../api";
import { LEVEL_COLOR } from "../../format";

/**
 * Спарклайн ветра: линия устойчивого ветра, тонкая линия порывов, зоны
 * порогов предиктора, отметка «сейчас». Свой SVG — без библиотек.
 */

interface Props {
  forecast: WindHour[];
  thresholds: Thresholds;
  now: Date;
  width?: number;
  height?: number;
}

const PAD = { top: 6, right: 8, bottom: 16, left: 26 };

export function WindSparkline({ forecast, thresholds, now, width = 320, height = 96 }: Props) {
  if (forecast.length < 2) return null;
  const t0 = Date.parse(forecast[0].ts);
  const t1 = Date.parse(forecast[forecast.length - 1].ts);
  const maxV = Math.max(
    thresholds.critical_wind + 4,
    ...forecast.map((h) => Math.max(h.speed, h.gust)),
  );
  const w = width - PAD.left - PAD.right;
  const h = height - PAD.top - PAD.bottom;
  const x = (ts: number) => PAD.left + ((ts - t0) / (t1 - t0)) * w;
  const y = (v: number) => PAD.top + h - (Math.min(v, maxV) / maxV) * h;
  const path = (key: "speed" | "gust") =>
    forecast
      .map((p, i) => `${i ? "L" : "M"}${x(Date.parse(p.ts)).toFixed(1)},${y(p[key]).toFixed(1)}`)
      .join(" ");
  const area = `${path("speed")} L${x(t1).toFixed(1)},${(PAD.top + h).toFixed(1)} L${x(t0).toFixed(1)},${(PAD.top + h).toFixed(1)} Z`;
  const nowX = x(Math.min(Math.max(now.getTime(), t0), t1));
  const bands: { from: number; to: number; color: string }[] = [
    { from: thresholds.watch_wind, to: thresholds.warning_wind, color: LEVEL_COLOR.watch },
    { from: thresholds.warning_wind, to: thresholds.critical_wind, color: LEVEL_COLOR.warning },
    { from: thresholds.critical_wind, to: maxV, color: LEVEL_COLOR.critical },
  ];
  const ticks = [-6, 0, 12, 24, 36, 48].filter((hh) => {
    const ts = now.getTime() + hh * 3_600_000;
    return ts >= t0 - 1 && ts <= t1 + 1;
  });

  return (
    <svg
      className="spark"
      viewBox={`0 0 ${width} ${height}`}
      width="100%"
      height={height}
      role="img"
      aria-label="Прогноз ветра на 48 часов с порогами предиктора"
    >
      <title>Прогноз ветра, м/с</title>
      {bands.map((b) => (
        <rect
          key={b.from}
          x={PAD.left}
          y={y(b.to)}
          width={w}
          height={Math.max(0, y(b.from) - y(b.to))}
          fill={b.color}
          opacity={0.1}
        />
      ))}
      {[thresholds.watch_wind, thresholds.warning_wind, thresholds.critical_wind].map((v, i) => (
        <g key={v}>
          <line
            x1={PAD.left}
            x2={PAD.left + w}
            y1={y(v)}
            y2={y(v)}
            stroke={[LEVEL_COLOR.watch, LEVEL_COLOR.warning, LEVEL_COLOR.critical][i]}
            strokeDasharray="2 3"
            opacity={0.6}
          />
          <text x={PAD.left - 4} y={y(v) + 3} className="spark__label" textAnchor="end">
            {v}
          </text>
        </g>
      ))}
      <path d={area} className="spark__area" />
      <path d={path("gust")} className="spark__gust" />
      <path d={path("speed")} className="spark__line" />
      <line x1={nowX} x2={nowX} y1={PAD.top} y2={PAD.top + h} className="spark__now" />
      {ticks.map((hh) => {
        const tx = x(now.getTime() + hh * 3_600_000);
        return (
          <text key={hh} x={tx} y={height - 4} className="spark__label" textAnchor="middle">
            {hh === 0 ? "сейчас" : hh > 0 ? `+${hh} ч` : `${hh} ч`}
          </text>
        );
      })}
    </svg>
  );
}
