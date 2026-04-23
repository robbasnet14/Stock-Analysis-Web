type SignalCardProps = {
  ticker: string;
  signal: "Bullish" | "Bearish" | "Neutral" | string;
  score: number;
  explanation: string;
  triggeredRules?: string[];
};

export function SignalCard({ ticker, signal, score, explanation, triggeredRules }: SignalCardProps) {
  const tone =
    signal.toLowerCase() === "bullish"
      ? "bg-emerald-500/20 text-emerald-500 dark:text-emerald-300"
      : signal.toLowerCase() === "bearish"
        ? "bg-rose-500/20 text-rose-500 dark:text-rose-300"
        : "bg-slate-400/20 text-slate-500 dark:text-slate-300";
  return (
    <article
      title={explanation}
      className="rounded-xl border border-slate-300 bg-white/80 p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900/70"
    >
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold">{ticker}</h3>
        <span className={`rounded-full px-2 py-1 text-xs font-semibold ${tone}`}>
          {signal}
        </span>
      </div>
      <p className="mt-2 text-sm font-semibold">Score: {score.toFixed(2)}</p>
      {triggeredRules && triggeredRules.length ? (
        <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">Triggered rules: {triggeredRules.join(", ")}</p>
      ) : null}
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{explanation}</p>
    </article>
  );
}
