import { LEVEL_COLOR } from "../format";

export function Legend() {
  return (
    <aside className="legend">
      <div className="legend__title">Легенда</div>
      <div className="legend__row">
        <span className="legend__dot" style={{ background: LEVEL_COLOR.ok }} />
        порт: норма
      </div>
      <div className="legend__row">
        <span className="legend__dot" style={{ background: LEVEL_COLOR.watch }} />◔ усиление ветра
      </div>
      <div className="legend__row">
        <span className="legend__dot" style={{ background: LEVEL_COLOR.warning }} />▲ риск остановки
      </div>
      <div className="legend__row">
        <span className="legend__dot" style={{ background: LEVEL_COLOR.critical }} />● вероятна остановка
      </div>
      <div className="legend__sep" />
      <div className="legend__row">
        <span className="legend__dot legend__dot--cargo" />
        груз: подтверждённая позиция
      </div>
      <div className="legend__row">
        <span className="legend__dot legend__dot--cargo legend__dot--proj" />
        груз: оценка по расписанию
      </div>
      <div className="legend__row">
        <span className="legend__ship">▲</span>
        паром (AIS)
      </div>
      <div className="legend__row">
        <span className="legend__wind">➜</span>
        ветер: куда дует, ярче = сильнее
      </div>
    </aside>
  );
}
