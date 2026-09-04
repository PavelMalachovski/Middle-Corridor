import { AVAILABLE_BASEMAPS, type BasemapId } from "../map/style";

interface Props {
  basemap: BasemapId;
  globe: boolean;
  terrain: boolean;
  fallback: boolean; // векторный стиль недоступен — показываем растровую подложку
  onBasemap: (id: BasemapId) => void;
  onGlobe: (on: boolean) => void;
  onTerrain: (on: boolean) => void;
}

export function MapControls({
  basemap,
  globe,
  terrain,
  fallback,
  onBasemap,
  onGlobe,
  onTerrain,
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
        <label className="switch">
          <input type="checkbox" checked={terrain} onChange={(e) => onTerrain(e.target.checked)} />
          <span>Рельеф</span>
        </label>
      </div>
      {fallback && (
        <div className="mapctl__hint" title="Векторные тайлы не ответили — включена растровая подложка">
          векторный стиль недоступен · растр
        </div>
      )}
    </aside>
  );
}
