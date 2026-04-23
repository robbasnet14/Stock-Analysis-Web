import { ChartRange } from "../../hooks/usePortfolioSeries";

const RANGES: ChartRange[] = ["1D", "1W", "1M", "3M", "1Y", "ALL"];

export function RangePicker({ value, onChange }: { value: ChartRange; onChange: (r: ChartRange) => void }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {RANGES.map((range) => (
        <button
          key={range}
          type="button"
          onClick={() => onChange(range)}
          className={`min-h-9 rounded-full px-3 py-2 text-sm font-semibold sm:min-h-0 sm:py-1 sm:text-xs ${
            value === range ? "bg-cyan-500 text-slate-950" : "bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300"
          }`}
        >
          {range}
        </button>
      ))}
    </div>
  );
}
