import { NewsItem } from "../types/api";

interface NewsPanelProps {
  news: NewsItem[];
}

export function NewsPanel({ news }: NewsPanelProps) {
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Latest Market News</h2>
        <span>Auto-refreshed headlines and sentiment score</span>
      </div>
      <div className="news-list">
        {news.slice(0, 8).map((item) => (
          <article key={item.id} className="news-item">
            <p className="news-meta">
              {item.source} · {new Date(item.publishedAt).toLocaleTimeString()} · Sent {item.sentimentScore}
            </p>
            <a href={item.url} target="_blank" rel="noreferrer">
              {item.headline}
            </a>
            <p>{item.summary}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
