import { BullCaseItem } from "../types";

interface Props {
  items: BullCaseItem[];
  horizon: "short" | "mid" | "long";
}

export function BullCaseBoard({ items, horizon }: Props) {
  const title = horizon === "short" ? "Bull Case Stocks (Next Days)" : horizon === "mid" ? "Bull Case Stocks (Next Weeks)" : "Bull Case Stocks (Long Horizon)";
  return (
    <section className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
      <h3 className="text-lg font-semibold text-slate-100">{title}</h3>
      <p className="mt-1 text-xs text-slate-400">Ranked by momentum, sentiment, volume, and trend for the selected horizon.</p>
      <div className="mt-3 space-y-2">
        {items.slice(0, 8).map((item) => (
          <div key={item.ticker} className="rounded-md border border-emerald-500/30 bg-slate-950/70 px-3 py-2">
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold text-slate-100">{item.ticker}</span>
              <span className="text-xs text-emerald-300">Score {item.score.toFixed(2)}</span>
            </div>
            <div className="mt-1 flex items-center justify-between text-xs text-slate-300">
              <span>${item.price.toFixed(2)}</span>
              <span className="text-emerald-300">+{item.change_percent.toFixed(2)}%</span>
              <span>Mom {item.momentum_percent.toFixed(2)}%</span>
              <span>Vol {item.volume_ratio.toFixed(2)}x</span>
            </div>
            <p className="mt-1 text-[11px] text-slate-400">{item.reasons.join(" · ")}</p>
          </div>
        ))}
        {items.length === 0 ? <p className="text-xs text-slate-400">No strong live bull setups right now.</p> : null}
      </div>
    </section>
  );
}
