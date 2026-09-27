import type { CheckpointDelay } from "../../forecast";
import { useI18n } from "../../i18n";

/**
 * Задержка по чекпоинтам: столбики «факт − план» в часах; будущие узлы —
 * штрихом, по текущей задержке груза.
 */

interface Props {
  delays: CheckpointDelay[];
  height?: number;
  nameOf?: (d: CheckpointDelay) => string; // подпись узла на языке интерфейса
}

const PAD = { top: 12, right: 6, bottom: 16, left: 6 };

export function DelayChart({ delays, height = 78, nameOf = (d) => d.name }: Props) {
  const { t } = useI18n();
  const hourUnit = t("common.h");
  if (delays.length < 2) return null;
  const width = 320;
  const w = width - PAD.left - PAD.right;
  const h = height - PAD.top - PAD.bottom;
  const maxAbs = Math.max(2, ...delays.map((d) => Math.abs(d.hours)));
  const zero = PAD.top + h * (maxAbs / (2 * maxAbs));
  const scale = h / (2 * maxAbs);
  const slot = w / delays.length;
  const bar = Math.max(4, Math.min(18, slot * 0.5));
  return (
    <svg
      className="delay"
      viewBox={`0 0 ${width} ${height}`}
      width="100%"
      height={height}
      role="img"
      aria-label={t("chart.delayAria")}
    >
      <title>{t("chart.delayTitle")}</title>
      <line x1={PAD.left} x2={PAD.left + w} y1={zero} y2={zero} className="delay__zero" />
      {delays.map((d, i) => {
        const cx = PAD.left + slot * (i + 0.5);
        // прогнозные столбики одинаковы — подписываем только первый, чтобы не шуметь
        const labelled = Math.abs(d.hours) >= 1 && (!d.projected || !delays[i - 1]?.projected);
        const hh = Math.abs(d.hours) * scale;
        const yTop = d.hours >= 0 ? zero - hh : zero;
        const cls = `delay__bar ${d.hours > 0.5 ? "is-late" : d.hours < -0.5 ? "is-early" : ""} ${d.projected ? "is-projected" : ""}`;
        const value = `${d.hours > 0 ? "+" : ""}${Math.round(d.hours)} ${hourUnit}`;
        return (
          <g key={d.code}>
            <title>
              {`${nameOf(d)}: ${value}${d.projected ? ` · ${t("chart.projected")}` : ""}`}
            </title>
            <rect
              x={cx - bar / 2}
              y={yTop}
              width={bar}
              height={Math.max(hh, 1)}
              className={cls}
              rx={1.5}
            />
            {labelled && (
              <text
                x={cx}
                y={d.hours >= 0 ? yTop - 3 : yTop + hh + 9}
                className="spark__label"
                textAnchor="middle"
              >
                {d.hours > 0 ? `+${Math.round(d.hours)}` : Math.round(d.hours)}
              </text>
            )}
          </g>
        );
      })}
      {/* начало и конец маршрута под осью — чтобы столбики читались как путь */}
      <text x={PAD.left} y={height - 3} className="spark__label">
        {nameOf(delays[0])}
      </text>
      <text x={PAD.left + w} y={height - 3} className="spark__label" textAnchor="end">
        {nameOf(delays[delays.length - 1])}
      </text>
    </svg>
  );
}
