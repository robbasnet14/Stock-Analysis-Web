import { useState } from "react";
import { NewsCard } from "../components/news/NewsCard";
import { SentimentBadge } from "../components/news/SentimentBadge";
import { TickerSearch } from "../components/portfolio/TickerSearch";
import { useNewsStream } from "../hooks/useNewsStream";

export default function News() {
  const [ticker, setTicker] = useState("AAPL");
  const tickerPills = ["AAPL", "MSFT", "NVDA", "TSLA", "SPY", "QQQ", "BTC-USD", "ETH-USD"];
  const { items, averageSentiment, loading } = useNewsStream(ticker);

  return (
    <section className="space-y-4">
      <header className="rounded-xl border border-slate-300 bg-white/80 p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900/70">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold">Market News</h1>
            <p className="text-sm text-slate-600 dark:text-slate-300">Auto-refreshing ticker news with sentiment overlays.</p>
            <div className="mt-2 flex items-center gap-2">
              <span className="text-xs text-slate-500 dark:text-slate-400">Ticker {ticker}</span>
              <SentimentBadge label={averageSentiment > 0.1 ? "positive" : averageSentiment < -0.1 ? "negative" : "neutral"} />
            </div>
          </div>
          <TickerSearch onSelect={setTicker} />
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {tickerPills.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTicker(t)}
              className={`rounded-full px-2 py-1 text-xs ${ticker === t ? "bg-cyan-500 text-slate-950" : "bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300"}`}
            >
              {t}
            </button>
          ))}
        </div>
      </header>

      {loading ? <p className="text-sm text-slate-500 dark:text-slate-400">Loading news stream...</p> : null}

      <div className="grid gap-3">
        {items.map((article) => (
          <NewsCard key={`${article.url}-${article.published_at}`} article={article} />
        ))}
        {!items.length && !loading ? (
          <div className="rounded-xl border border-slate-300 bg-white/80 p-4 text-sm dark:border-slate-700 dark:bg-slate-900/70">
            No news currently available for this ticker.
          </div>
        ) : null}
      </div>
    </section>
  );
}
