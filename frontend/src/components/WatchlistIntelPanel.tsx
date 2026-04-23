import { WatchlistIntelItem } from "../types";

interface Props {
  items: WatchlistIntelItem[];
}

function badgeClass(label: string): string {
  if (label === "positive" || label === "bullish" || label === "buy") return "text-emerald-300";
  if (label === "negative" || label === "bearish" || label === "sell") return "text-rose-300";
  return "text-slate-300";
}

export function WatchlistIntelPanel({ items }: Props) {
  return (
    <section className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
      <h3 className="text-lg font-semibold text-slate-100">Watchlist Intelligence</h3>
      <p className="mt-1 text-xs text-slate-400">Sentiment, momentum, analyst-style rating, and risk for your watchlist.</p>
      <div className="mt-3 space-y-2">
        {items.slice(0, 8).map((item) => (
          <div key={item.symbol} className="rounded border border-slate-700 bg-slate-950/70 p-2 text-xs">
            <div className="flex items-center justify-between">
              <p className="font-semibold text-slate-100">{item.symbol}</p>
              <p className={item.change_percent >= 0 ? "text-emerald-300" : "text-rose-300"}>
                {item.change_percent >= 0 ? "+" : ""}{item.change_percent.toFixed(2)}%
              </p>
            </div>
            <p className="mt-1 text-slate-400">
              Sentiment <span className={badgeClass(item.sentiment)}>{item.sentiment}</span> · Momentum{" "}
              <span className={badgeClass(item.momentum)}>{item.momentum}</span>
            </p>
            <p className="text-slate-400">
              Analyst <span className={badgeClass(item.analyst_rating)}>{item.analyst_rating}</span> · Risk{" "}
              <span className="text-amber-300">{item.risk_level}</span> · Vol {item.volume_ratio.toFixed(2)}x
            </p>
          </div>
        ))}
        {items.length === 0 ? <p className="text-xs text-slate-400">No watchlist intelligence yet.</p> : null}
      </div>
    </section>
  );
}
