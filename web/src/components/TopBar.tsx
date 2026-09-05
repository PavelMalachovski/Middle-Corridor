import { useEffect, useState } from "react";
import type { Snapshot } from "../api";
import { fmtTs } from "../format";
import { type Key, type Lang, useI18n } from "../i18n";
import type { LiveMode } from "../live";
import type { LayerToggles } from "../map/MapView";

interface Props {
  snapshot: Snapshot | null;
  error: string | null;
  fetchedAt: Date | null;
  mode: LiveMode;
  layers: LayerToggles;
  windAvailable: boolean;
  onToggle: (key: keyof LayerToggles) => void;
}

const TOGGLES: (keyof LayerToggles)[] = ["shipments", "vessels", "wind", "routes"];
const LANGS: Lang[] = ["ru", "en"];

export function TopBar({
  snapshot,
  error,
  fetchedAt,
  mode,
  layers,
  windAvailable,
  onToggle,
}: Props) {
  const { t, lang, setLang } = useI18n();
  const [, setTick] = useState(0); // перерисовка «N с назад» раз в секунду
  useEffect(() => {
    const timer = setInterval(() => setTick((v) => v + 1), 1000);
    return () => clearInterval(timer);
  }, []);
  const ageSec = fetchedAt
    ? Math.max(0, Math.round((Date.now() - fetchedAt.getTime()) / 1000))
    : null;
  const [online, setOnline] = useState(() =>
    typeof navigator === "undefined" ? true : navigator.onLine,
  );
  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, []);
  // снимок старше трёх интервалов обновления — данные не живые (офлайн, кэш сервис-воркера)
  const stale =
    snapshot != null &&
    ageSec != null &&
    mode !== "replay" &&
    ageSec > snapshot.live.refresh_s * 3 + 5;
  const inTransit = snapshot?.shipments.filter((s) => s.state === "in_transit").length ?? 0;
  const delayed =
    snapshot?.shipments.filter((s) => s.delay_hours >= 1 && s.state !== "delivered").length ?? 0;
  const alerts =
    snapshot?.nodes.filter((n) => n.alert_level === "warning" || n.alert_level === "critical")
      .length ?? 0;
  const errorCode = error?.match(/HTTP \d{3}/)?.[0] ?? null; // 404 = нет бэкенда, 5xx = упал
  const hourUnit = t("common.h");

  return (
    <header className="topbar">
      <div className="topbar__brand">
        <div className="topbar__title">Middle Corridor</div>
        <div className="topbar__subtitle">{t("app.subtitle")}</div>
      </div>
      {snapshot?.mock && (
        <span className="badge badge--mock" title={t("top.mockTitle")}>
          MOCK DATA
        </span>
      )}
      <div className="topbar__kpis">
        <span className="kpi">
          <b>{inTransit}</b> {t("top.inTransit")}
        </span>
        <span className={`kpi ${delayed ? "kpi--warn" : ""}`}>
          <b>{delayed}</b> {t("top.delayed")}
        </span>
        <span className={`kpi ${alerts ? "kpi--alert" : ""}`}>
          <b>{alerts}</b> {alerts === 1 ? t("top.portAtRisk") : t("top.portsAtRisk")}
        </span>
      </div>
      {snapshot?.summary && (
        <div className="topbar__week" title={t("top.weekTitle")}>
          <span>
            {t("top.week")} <b>{snapshot.summary.caspian_crossings}</b> {t("top.weekCrossings")}
          </span>
          <span>
            {t("top.weekDelay")}{" "}
            <b>
              {snapshot.summary.avg_delay_hours == null
                ? "—"
                : `${Math.round(snapshot.summary.avg_delay_hours)} ${hourUnit}`}
            </b>
          </span>
          {snapshot.summary.port_downtime_hours != null && (
            <span>
              {t("top.weekDowntime")}{" "}
              <b>
                {Math.round(snapshot.summary.port_downtime_hours)} {hourUnit}
              </b>
              {snapshot.summary.ports_stopped ? ` (${snapshot.summary.ports_stopped})` : ""}
            </span>
          )}
        </div>
      )}
      <div className="topbar__layers">
        {TOGGLES.map((key) => (
          <button
            key={key}
            type="button"
            className={`chip ${layers[key] ? "chip--on" : ""}`}
            onClick={() => onToggle(key)}
            disabled={key === "wind" && !windAvailable}
            title={key === "wind" && !windAvailable ? t("layer.windUnavailable") : undefined}
          >
            {t(`layer.${key}` as Key)}
          </button>
        ))}
        <fieldset className="lang">
          <legend className="sr-only">{t("lang.switch")}</legend>
          {LANGS.map((code) => (
            <button
              key={code}
              type="button"
              className={`lang__btn ${lang === code ? "is-on" : ""}`}
              onClick={() => setLang(code)}
              aria-pressed={lang === code}
            >
              {code.toUpperCase()}
            </button>
          ))}
        </fieldset>
      </div>
      <div className={`topbar__status ${error ? "topbar__status--error" : ""}`}>
        {error ? (
          <span title={error}>
            {t("top.noApi")}
            {errorCode ? ` · ${errorCode}` : ""}
          </span>
        ) : ageSec == null ? (
          <span>{t("common.loading")}</span>
        ) : (!online || stale) && snapshot ? (
          <span
            className="topbar__stale"
            title={online ? t("top.staleTitle") : t("top.offlineTitle")}
          >
            <i className="dot-live dot-live--stale" /> {online ? t("top.stale") : t("top.offline")}{" "}
            · {t("top.dataAt", { ts: fmtTs(snapshot.generated_at) })}
          </span>
        ) : mode === "replay" && snapshot ? (
          <span title={t("top.replayTitle")}>
            <i className="dot-live dot-live--replay" />{" "}
            {t("top.replayAt", { ts: fmtTs(snapshot.generated_at) })}
          </span>
        ) : (
          <span>
            <i className="dot-live" />{" "}
            {t("top.updated", { sec: ageSec, mode: t(`top.mode.${mode}` as Key) })}
          </span>
        )}
      </div>
    </header>
  );
}
