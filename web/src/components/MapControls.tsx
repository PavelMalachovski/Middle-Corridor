import type { WindMode } from "../map/MapView";
import { AVAILABLE_BASEMAPS, type BasemapId } from "../map/style";

interface Props {
  basemap: BasemapId;
  globe: boolean;
  terrain: boolean;
  terrain3d: boolean;
  fallback: boolean; // векторный стиль недоступен — показываем растровую подложку
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
  onBasemap,
  onGlobe,
  onTerrain,
  onTerrain3d,
  windMode,
  windHint,
  onWindMode,
}: Props) {
  return (
    <aside className="mapctl">
      <div className="mapctl__title">Подложка</div>
      <div className="mapctl__row">
        {AVAILABLE_BASEMAPS.map((preset) => (
          <button
            key={preset.id}
            type="button"
            className={`chip ${basemap === preset.id ? "chip--on" : ""}`}
            title={preset.hint}
            onClick={() => onBasemap(preset.id)}
          >
            {preset.label}
          </button>
        ))}
      </div>
      <div className="mapctl__row">
        <label className="switch">
          <input type="checkbox" checked={globe} onChange={(e) => onGlobe(e.target.checked)} />
          <span>Глобус</span>
        </label>
        <label className="switch" title="Светотень рельефа поверх подложки">
          <input
            type="checkbox"
            checked={terrain || terrain3d}
            disabled={terrain3d}
            onChange={(e) => onTerrain(e.target.checked)}
          />
          <span>Рельеф</span>
        </label>
        <label
          className="switch"
          title="Объёмный рельеф и наклон камеры; вращение — правой кнопкой или компасом"
        >
          <input
            type="checkbox"
            checked={terrain3d}
            onChange={(e) => onTerrain3d(e.target.checked)}
          />
          <span>3D</span>
        </label>
      </div>
      <div className="mapctl__row">
        <span className="mapctl__label">Ветер</span>
        <button
          type="button"
          className={`chip ${windMode === "particles" ? "chip--on" : ""}`}
          title="Живые частицы по полю ветра (WebGL); цвет — сила ветра"
          onClick={() => onWindMode("particles")}
        >
          Частицы
        </button>
        <button
          type="button"
          className={`chip ${windMode === "arrows" ? "chip--on" : ""}`}
          title="Стрелки по сетке — легче для слабых устройств"
          onClick={() => onWindMode("arrows")}
        >
          Стрелки
        </button>
      </div>
      {windHint && (
        <div className="mapctl__hint">частицы выключены: устройству тяжело, показаны стрелки</div>
      )}
      {fallback && (
        <div
          className="mapctl__hint"
          title="Векторные тайлы не ответили — включена растровая подложка"
        >
          векторный стиль недоступен · растр
        </div>
      )}
    </aside>
  );
}
