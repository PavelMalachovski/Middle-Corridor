import type { Snapshot } from "../api";
import { fmtRelative } from "../format";
import { useI18n } from "../i18n";

export function NewsPanel({ snapshot }: { snapshot: Snapshot }) {
  const { t } = useI18n();
  const ref = new Date(snapshot.generated_at);
  if (!snapshot.news.length) {
    return <div className="empty">{t("news.empty")}</div>;
  }
  return (
    <ul className="list">
      {snapshot.news.map((n) => (
        <li key={n.id} className="card news">
          <div className="news__meta">
            <span className="news__source">{n.source}</span>
            <span className="muted">{fmtRelative(n.published_at, ref)}</span>
          </div>
          <a className="news__title" href={n.url} target="_blank" rel="noreferrer">
            {n.title}
          </a>
          {n.summary && <div className="news__summary">{n.summary}</div>}
        </li>
      ))}
    </ul>
  );
}
