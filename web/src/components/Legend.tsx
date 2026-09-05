import { LEVEL_COLOR } from "../format";
import { useI18n } from "../i18n";

export function Legend() {
  const { t } = useI18n();
  return (
    <aside className="legend">
      <div className="legend__title">{t("legend.title")}</div>
      <div className="legend__row">
        <span className="legend__dot" style={{ background: LEVEL_COLOR.ok }} />
        {t("legend.portOk")}
      </div>
      <div className="legend__row">
        <span className="legend__dot" style={{ background: LEVEL_COLOR.watch }} />
        {t("legend.watch")}
      </div>
      <div className="legend__row">
        <span className="legend__dot" style={{ background: LEVEL_COLOR.warning }} />
        {t("legend.warning")}
      </div>
      <div className="legend__row">
        <span className="legend__dot" style={{ background: LEVEL_COLOR.critical }} />
        {t("legend.critical")}
      </div>
      <div className="legend__sep" />
      <div className="legend__row">
        <span className="legend__ribbon" />
        {t("legend.corridor")}
      </div>
      <div className="legend__row">
        <span className="legend__dot legend__dot--cargo" />
        {t("legend.cargoConfirmed")}
      </div>
      <div className="legend__row">
        <span className="legend__dot legend__dot--cargo legend__dot--proj" />
        {t("legend.cargoProjected")}
      </div>
      <div className="legend__row">
        <span className="legend__ship">▲</span>
        {t("legend.ferry")}
      </div>
      <div className="legend__row">
        <span className="legend__wind">➜</span>
        {t("legend.wind")}
      </div>
    </aside>
  );
}
