import { NewsArticle } from "../types";

interface Props {
  items: NewsArticle[];
  averageSentiment: number;
}

function sentimentColor(label: string) {
  if (label === "positive") return "text-emerald-300";
  if (label === "negative") return "text-rose-300";
  return "text-amber-200";
}

export function NewsFeed({ items, averageSentiment }: Props) {
  return (
    <section className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold text-slate-100">Latest News</h3>
        <span className="text-xs text-slate-400">Avg Sentiment: {averageSentiment.toFixed(2)}</span>
      </div>
      <div className="space-y-2">
        {items.slice(0, 8).map((item, idx) => (
          <article key={`${item.url}-${idx}`} className="rounded-lg border border-slate-700 bg-slate-950/70 p-3">
            <div className="mb-1 flex justify-between text-xs text-slate-400">
              <span>{item.source}</span>
              <span>{new Date(item.published_at).toLocaleTimeString()}</span>
            </div>
            <a href={item.url} target="_blank" rel="noreferrer" className="text-sm font-medium text-cyan-300 hover:text-cyan-200">
              {item.headline}
            </a>
            <p className="mt-1 text-xs text-slate-300">{item.summary}</p>
            <p className={`mt-1 text-xs ${sentimentColor(item.sentiment_label)}`}>
              {item.sentiment_label} ({item.sentiment_score.toFixed(2)})
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}
