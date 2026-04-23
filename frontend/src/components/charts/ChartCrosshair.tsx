import { PricePoint } from "../../types";

export function ChartCrosshair({ point }: { point: PricePoint | null }) {
  if (!point) {
    return <p className="text-xs text-slate-500 dark:text-slate-400">Hover chart for price/time.</p>;
  }

  return (
    <div className="rounded-md border border-slate-300 bg-white/80 px-3 py-2 text-xs shadow-sm dark:border-slate-700 dark:bg-slate-900/80">
      <p className="font-semibold">${point.price.toFixed(2)}</p>
      <p className="text-slate-500 dark:text-slate-400">{new Date(point.timestamp).toLocaleString()}</p>
    </div>
  );
}
