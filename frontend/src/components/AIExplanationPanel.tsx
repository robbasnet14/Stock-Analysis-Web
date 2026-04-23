interface Props {
  ticker: string;
  horizon: "short" | "mid" | "long";
  explanation: string;
}

export function AIExplanationPanel({ ticker, horizon, explanation }: Props) {
  return (
    <section className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
      <h3 className="text-lg font-semibold text-slate-100">AI Explanation</h3>
      <p className="mt-1 text-xs text-slate-400">Narrative generated from model and market factors for {ticker} ({horizon}).</p>
      <p className="mt-3 rounded border border-cyan-500/30 bg-cyan-500/10 p-3 text-sm text-cyan-100">
        {explanation || "Generating explanation..."}
      </p>
    </section>
  );
}
