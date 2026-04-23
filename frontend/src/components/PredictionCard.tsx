import { Prediction } from "../types";

interface Props {
  prediction: Prediction | null;
  explanation: string;
}

export function PredictionCard({ prediction, explanation }: Props) {
  if (!prediction) {
    return (
      <section className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
        <h3 className="text-lg font-semibold text-slate-100">Bull / Bear Prediction</h3>
        <p className="mt-2 text-sm text-slate-300">Model warming up...</p>
      </section>
    );
  }

  const bull = Math.round(prediction.bull_probability * 100);
  const bear = Math.round(prediction.bear_probability * 100);

  return (
    <section className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
      <h3 className="text-lg font-semibold text-slate-100">Bull / Bear Indicator</h3>
      <div className="mt-3 grid grid-cols-2 gap-3">
        <div className="rounded-lg border border-emerald-400/40 bg-emerald-500/10 p-3 text-center">
          <p className="text-xs text-slate-300">Bull</p>
          <p className="text-2xl font-semibold text-emerald-300">{bull}%</p>
        </div>
        <div className="rounded-lg border border-rose-400/40 bg-rose-500/10 p-3 text-center">
          <p className="text-xs text-slate-300">Bear</p>
          <p className="text-2xl font-semibold text-rose-300">{bear}%</p>
        </div>
      </div>

      <div className="mt-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Reasons</p>
        <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-slate-200">
          {prediction.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      </div>

      <p className="mt-3 rounded-md bg-slate-950/70 p-2 text-xs text-cyan-200">AI explanation: {explanation}</p>
    </section>
  );
}
