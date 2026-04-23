import { SignalCard } from "./SignalCard";

type EnsembleRow = {
  ticker: string;
  score: number;
  confidence?: number;
  narrative?: string;
  contributions?: Record<string, number>;
};

function pct(v: number) {
  return `${Math.max(0, Math.min(100, v * 100)).toFixed(1)}%`;
}

export function EnsembleTrack({ items }: { items: EnsembleRow[] }) {
  if (!items.length) {
    return <p className="text-sm text-slate-500 dark:text-slate-400">No ensemble ranking data yet.</p>;
  }

  return (
    <div className="grid gap-3">
      {items.map((row) => {
        const scorePct = Math.max(0, Math.min(100, ((row.score + 1) / 2) * 100));
        const contributionSummary = row.contributions
          ? Object.entries(row.contributions)
              .map(([k, v]) => `${k.replace("_model", "")}:${(v * 100).toFixed(1)}%`)
              .join(" · ")
          : "";
        return (
          <div key={row.ticker} className="rounded-xl border border-slate-300 bg-white/80 p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900/70">
            <div className="mb-2 h-2 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
              <div className="h-2 bg-cyan-500" style={{ width: `${scorePct}%` }} />
            </div>
            <SignalCard
              ticker={row.ticker}
              signal={row.score > 0.2 ? "Bullish" : row.score < -0.2 ? "Bearish" : "Neutral"}
              score={scorePct}
              explanation={`${row.narrative || `Final ${pct(row.score)} · Confidence ${pct(row.confidence ?? 0.5)}`}${contributionSummary ? ` | ${contributionSummary}` : ""}`}
            />
          </div>
        );
      })}
    </div>
  );
}

export type { EnsembleRow };
