import { MarketPulse } from "../types";

interface Props {
  pulse: MarketPulse | null;
}

function pctClass(value: number): string {
  return value >= 0 ? "text-emerald-300" : "text-rose-300";
}

export function MarketPulsePanel({ pulse }: Props) {
  return (
    <section className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
      <h3 className="text-lg font-semibold text-slate-100">Market Pulse</h3>
      {!pulse ? <p className="mt-2 text-xs text-slate-400">Loading pulse...</p> : null}

      {pulse ? (
        <div className="mt-3 space-y-3">
          <div className="grid grid-cols-3 gap-2">
            {Object.values(pulse.indices).map((idx) => (
              <div key={idx.symbol} className="rounded border border-slate-700 bg-slate-950/70 p-2 text-xs">
                <p className="font-semibold text-slate-100">{idx.symbol}</p>
                <p className={pctClass(idx.change_percent)}>{idx.change_percent >= 0 ? "+" : ""}{idx.change_percent.toFixed(2)}%</p>
              </div>
            ))}
          </div>
          <div className="grid gap-2 md:grid-cols-2">
            <div className="rounded border border-slate-700 bg-slate-950/70 p-2 text-xs">
              <p className="mb-1 font-semibold text-slate-200">Top Gainers</p>
              {pulse.top_gainers.slice(0, 5).map((r) => (
                <p key={r.symbol} className="text-slate-300">{r.symbol} <span className="text-emerald-300">{r.change_percent.toFixed(2)}%</span></p>
              ))}
            </div>
            <div className="rounded border border-slate-700 bg-slate-950/70 p-2 text-xs">
              <p className="mb-1 font-semibold text-slate-200">Unusual Volume</p>
              {pulse.unusual_volume.slice(0, 5).map((r) => (
                <p key={r.symbol} className="text-slate-300">{r.symbol} <span className="text-cyan-300">{r.volume_ratio.toFixed(2)}x</span></p>
              ))}
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
