/**
 * Заглушка на месте карты: браузер без WebGL 2 или карта упала.
 * Панель справа продолжает работать — данные не зависят от карты.
 */

interface Props {
  title: string;
  detail: string;
  onRetry?: () => void;
}

export function MapFallback({ title, detail, onRetry }: Props) {
  return (
    <div className="map map--fallback" role="alert">
      <div className="map-fallback">
        <div className="map-fallback__icon" aria-hidden="true">
          🗺
        </div>
        <div className="map-fallback__title">{title}</div>
        <div className="map-fallback__detail">{detail}</div>
        {onRetry && (
          <button type="button" className="chip chip--on" onClick={onRetry}>
            Попробовать снова
          </button>
        )}
      </div>
    </div>
  );
}

/** MapLibre 6 рисует только через WebGL 2: старые WebView и Safari до 15 не подойдут. */
export function hasWebGL2(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return canvas.getContext("webgl2") !== null;
  } catch {
    return false;
  }
}
