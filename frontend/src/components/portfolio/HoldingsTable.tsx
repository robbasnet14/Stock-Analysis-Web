import { Position } from "../../types";
import { LatestPrice } from "../../store/portfolio";

export function HoldingsTable({
  holdings,
  latestPrices,
  onDelete,
  onEdit
}: {
  holdings: Position[];
  latestPrices: Record<string, LatestPrice>;
  onDelete?: (id: number) => Promise<void>;
  onEdit?: (row: Position) => void;
}) {
  if (!holdings.length) {
    return <p className="text-sm text-slate-500 dark:text-slate-400">No holdings yet. Add one to start portfolio tracking.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead>
          <tr className="border-b border-slate-300 text-slate-500 dark:border-slate-700 dark:text-slate-400">
            <th className="px-2 py-2">Ticker</th>
            <th className="px-2 py-2">Shares</th>
            <th className="px-2 py-2">Avg Cost</th>
            <th className="px-2 py-2">Live</th>
            <th className="px-2 py-2">P/L</th>
            <th className="px-2 py-2">Action</th>
          </tr>
        </thead>
        <tbody>
          {holdings.map((h) => {
            const live = latestPrices[h.ticker]?.price ?? 0;
            const value = live * h.quantity;
            const cost = h.avg_cost * h.quantity;
            const pnl = value - cost;
            const pnlPct = cost > 0 ? (pnl / cost) * 100 : 0;
            return (
              <tr key={h.id} className="border-b border-slate-200/60 dark:border-slate-800/70">
                <td className="px-2 py-2 font-semibold">{h.ticker}</td>
                <td className="px-2 py-2">{h.quantity.toFixed(4)}</td>
                <td className="px-2 py-2">${h.avg_cost.toFixed(2)}</td>
                <td className="px-2 py-2">${live.toFixed(2)}</td>
                <td className={`px-2 py-2 font-semibold ${pnl >= 0 ? "text-emerald-500" : "text-rose-500"}`}>
                  {pnl >= 0 ? "+" : ""}${pnl.toFixed(2)} ({pnlPct.toFixed(2)}%)
                </td>
                <td className="px-2 py-2">
                  {onDelete || onEdit ? (
                    <div className="flex items-center gap-2">
                      {onEdit ? (
                        <button
                          type="button"
                          onClick={() => onEdit(h)}
                          className="rounded border border-cyan-300 px-2 py-1 text-xs text-cyan-500 hover:bg-cyan-500/10"
                        >
                          Edit
                        </button>
                      ) : null}
                      {onDelete ? (
                        <button
                          type="button"
                          onClick={() => {
                            void onDelete(h.id);
                          }}
                          className="rounded border border-rose-300 px-2 py-1 text-xs text-rose-500 hover:bg-rose-500/10"
                        >
                          Remove
                        </button>
                      ) : null}
                    </div>
                  ) : (
                    <span className="text-xs text-slate-400">-</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
