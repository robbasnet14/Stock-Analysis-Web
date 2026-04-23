import { NewsArticle } from "../../types";
import { SentimentBadge } from "./SentimentBadge";

function relativeTime(ts: string) {
  const ms = Date.now() - new Date(ts).getTime();
  const m = Math.round(ms / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24);
  return `${d}d ago`;
}

export function NewsCard({ article }: { article: NewsArticle }) {
  return (
    <article className="rounded-xl border border-slate-300 bg-white/80 p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900/70">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-xs text-slate-500 dark:text-slate-400">{article.source}</p>
        <SentimentBadge label={article.sentiment_label || "neutral"} />
      </div>
      <h3 className="text-base font-semibold">{article.headline}</h3>
      <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">{article.summary}</p>
      <div className="mt-2 flex items-center gap-2">
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          {article.ticker}
        </span>
      </div>
      <div className="mt-3 flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
        <span>{relativeTime(article.published_at)}</span>
        <a href={article.url} target="_blank" rel="noreferrer" className="text-cyan-600 hover:underline dark:text-cyan-300">
          Open
        </a>
      </div>
    </article>
  );
}
