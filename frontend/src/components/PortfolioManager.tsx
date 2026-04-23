import { FormEvent, useEffect, useMemo, useState } from "react";
import { Position } from "../types";

interface Props {
  ticker: string;
  latestPrice: number;
  positions: Position[];
  onSavePosition: (ticker: string, quantity: number, avgCost: number) => Promise<void>;
  onDeletePosition: (id: number) => Promise<void>;
  canTrade: boolean;
}

export function PortfolioManager({
  ticker,
  latestPrice,
  positions,
  onSavePosition,
  onDeletePosition,
  canTrade
}: Props) {
  const [symbol, setSymbol] = useState(ticker);
  const [qty, setQty] = useState("");
  const [cost, setCost] = useState("");

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!canTrade) return;
    const resolvedTicker = symbol.trim().toUpperCase();
    const quantity = Number(qty);
    const avgCost = Number(cost);
    if (!resolvedTicker || !quantity || !avgCost) return;
    await onSavePosition(resolvedTicker, quantity, avgCost);
    setQty("");
    setCost("");
  }

  const totalPnl = useMemo(() => {
    return positions.reduce((acc, p) => acc + (latestPrice - p.avg_cost) * p.quantity, 0);
  }, [positions, latestPrice]);

  useEffect(() => {
    setSymbol(ticker);
  }, [ticker]);

  return (
    <section className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
      <h3 className="text-lg font-semibold text-slate-100">Saved Portfolio</h3>

      <form onSubmit={save} className="mt-2 flex gap-2">
        <input value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="Ticker" className="w-full rounded border border-slate-600 bg-slate-950 px-2 py-1 text-xs" />
        <input value={qty} onChange={(e) => setQty(e.target.value)} placeholder="Qty" className="w-full rounded border border-slate-600 bg-slate-950 px-2 py-1 text-xs" />
        <input value={cost} onChange={(e) => setCost(e.target.value)} placeholder="Avg cost" className="w-full rounded border border-slate-600 bg-slate-950 px-2 py-1 text-xs" />
        <button disabled={!canTrade} className="rounded bg-cyan-500 px-3 py-1 text-xs font-semibold text-slate-950 disabled:opacity-40">
          Save
        </button>
      </form>

      <div className="mt-3 space-y-1">
        {positions.map((p) => (
          <div key={p.id} className="flex items-center justify-between rounded border border-slate-700 bg-slate-950/60 px-2 py-1 text-xs">
            <span>
              {p.ticker} · {p.quantity} @ {p.avg_cost.toFixed(2)}
            </span>
            <button onClick={() => onDeletePosition(p.id)} className="text-rose-300">
              delete
            </button>
          </div>
        ))}
      </div>

      <p className={`mt-3 text-sm font-medium ${totalPnl >= 0 ? "text-emerald-300" : "text-rose-300"}`}>Unrealized P/L: {totalPnl.toFixed(2)} USD</p>
      {!canTrade ? <p className="mt-1 text-xs text-slate-400">Trader/admin role required to modify positions.</p> : null}
    </section>
  );
}
