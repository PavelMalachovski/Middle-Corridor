import { type Key, useI18n } from "../i18n";
import type { WindMode } from "../map/MapView";
import { AVAILABLE_BASEMAPS, type BasemapId } from "../map/style";

interface Props {
  basemap: BasemapId;
  globe: boolean;
  terrain: boolean;
  terrain3d: boolean;
  fallback: boolean; // векторный стиль недоступен — показываем растровую подложку
  software: boolean; // программный WebGL (SwiftShader/llvmpipe): 3D-рельеф не тянет
  onBasemap: (id: BasemapId) => void;
  onGlobe: (on: boolean) => void;
  onTerrain: (on: boolean) => void;
  onTerrain3d: (on: boolean) => void;
  windMode: WindMode;
  windHint: boolean; // частицы выключены автоматически — устройство не тянет
  onWindMode: (mode: WindMode) => void;
}

export function MapControls({
  basemap,
  globe,
  terrain,
  terrain3d,
  fallback,
  software,
  onBasemap,
  onGlobe,
  onTerrain,
  onTerrain3d,
  windMode,
  windHint,
  onWindMode,
}: Props) {
  const { t } = useI18n();
  return (
    <aside className="mapctl">
      <div className="mapctl__title">{t("ctl.basemap")}</div>
      <div className="mapctl__row">
        {AVAILABLE_BASEMAPS.map((preset) => (
          <button
            key={preset.id}
            type="button"
            className={`chip ${basemap === preset.id ? "chip--on" : ""}`}
            title={t(`${preset.label}.hint` as Key)}
            onClick={() => onBasemap(preset.id)}
          >
            {t(preset.label as Key)}
          </button>
        ))}
      </div>
      <div className="mapctl__row">
        <label className="switch">
          <input type="checkbox" checked={globe} onChange={(e) => onGlobe(e.target.checked)} />
          <span>{t("ctl.globe")}</span>
        </label>
        <label className="switch" title={t("ctl.terrainTitle")}>
          <input
            type="checkbox"
            checked={terrain || terrain3d}
            disabled={terrain3d}
            onChange={(e) => onTerrain(e.target.checked)}
          />
          <span>{t("ctl.terrain")}</span>
        </label>
        {!software && (
          <label className="switch" title={t("ctl.3dTitle")}>
            <input
              type="checkbox"
              checked={terrain3d}
              onChange={(e) => onTerrain3d(e.target.checked)}
            />
            <span>{t("ctl.3d")}</span>
          </label>
        )}
      </div>
      {software && <div className="mapctl__hint">{t("ctl.3dSoftware")}</div>}
      <div className="mapctl__row">
        <span className="mapctl__label">{t("ctl.wind")}</span>
        <button
          type="button"
          className={`chip ${windMode === "particles" ? "chip--on" : ""}`}
          title={t("ctl.particlesTitle")}
          onClick={() => onWindMode("particles")}
        >
          {t("ctl.particles")}
        </button>
        <button
          type="button"
          className={`chip ${windMode === "arrows" ? "chip--on" : ""}`}
          title={t("ctl.arrowsTitle")}
          onClick={() => onWindMode("arrows")}
        >
          {t("ctl.arrows")}
        </button>
      </div>
      {windHint && <div className="mapctl__hint">{t("ctl.windHint")}</div>}
      {fallback && (
        <div className="mapctl__hint" title={t("ctl.fallbackTitle")}>
          {t("ctl.fallback")}
        </div>
      )}
    </aside>
  );
}
