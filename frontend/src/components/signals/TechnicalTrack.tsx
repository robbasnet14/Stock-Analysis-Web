import { SignalCard } from "./SignalCard";

type DetailNav = {
  hrefForTicker?: (ticker: string) => string;
  onOpenTicker?: (ticker: string) => void;
};

type TechnicalRow = {
  ticker: string;
  score: number;
  confidence: number;
  explanation: string;
  action?: "bullish" | "bearish" | "neutral";
  status?: "ok" | "insufficient_data";
  triggered_rules?: string[];
  indicators: Array<{
    name: string;
    value: number;
    vote: number;
    fired_rule: string;
    explanation: string;
  }>;
};

export function TechnicalTrack({ items, hrefForTicker, onOpenTicker }: { items: TechnicalRow[] } & DetailNav) {
  if (!items.length) {
    return <p className="text-sm text-slate-500 dark:text-slate-400">No technical snapshots available yet.</p>;
  }

  return (
    <div className="grid gap-3">
      {items.map((row) => {
        const score = Math.max(0, Math.min(100, ((row.score + 1) / 2) * 100));
        const trend =
          row.action === "bullish"
            ? "Bullish"
            : row.action === "bearish"
              ? "Bearish"
              : "Neutral";
        const top = row.triggered_rules ?? [];
        const prefix = row.status === "insufficient_data" ? "Insufficient data." : row.explanation;
        return (
          <SignalCard
            key={row.ticker}
            ticker={row.ticker}
            signal={trend}
            score={score}
            triggeredRules={top}
            explanation={prefix}
            to={hrefForTicker ? hrefForTicker(row.ticker) : undefined}
            onOpen={onOpenTicker ? () => onOpenTicker(row.ticker) : undefined}
          />
        );
      })}
    </div>
  );
}

export type { TechnicalRow };
