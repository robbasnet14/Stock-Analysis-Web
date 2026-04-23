interface Props {
  darkPoolVolume: number;
  unusualOptionsScore: number;
  insiderBiasScore: number;
  sources: string[];
}

export function FlowPanel({ darkPoolVolume, unusualOptionsScore, insiderBiasScore, sources }: Props) {
  return (
    <section className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
      <h3 className="text-lg font-semibold text-slate-100">Insider / Options / Dark Pool</h3>
      <div className="mt-2 space-y-1 text-xs text-slate-200">
        <p>Dark Pool Volume: {darkPoolVolume.toLocaleString()}</p>
        <p>Unusual Options Score: {unusualOptionsScore.toFixed(3)}</p>
        <p>Insider Bias Score: {insiderBiasScore.toFixed(3)}</p>
      </div>
      <p className="mt-2 text-[11px] text-slate-400">Sources: {sources.join(", ")}</p>
    </section>
  );
}
