import { TrendingItem } from "../types";

interface Props {
  items: TrendingItem[];
}

export function TrendingStocks({ items }: Props) {
  return (
    <section className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
      <h3 className="text-lg font-semibold text-slate-100">Trending Stocks</h3>
      <div className="mt-3 space-y-2">
        {items.slice(0, 8).map((item) => (
          <div key={item.ticker} className="flex items-center justify-between rounded-md border border-slate-700 bg-slate-950/70 px-3 py-2">
            <span className="text-sm font-medium text-slate-100">{item.ticker}</span>
            <span className="text-sm text-slate-200">${item.price.toFixed(2)}</span>
            <span className={`text-xs ${item.change_percent >= 0 ? "text-emerald-300" : "text-rose-300"}`}>
              {item.change_percent.toFixed(2)}%
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
