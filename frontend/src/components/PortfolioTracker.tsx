import { useMemo, useState } from "react";

interface Holding {
  ticker: string;
  quantity: number;
  avgCost: number;
}

interface Props {
  latestPrice: number;
  ticker: string;
}

export function PortfolioTracker({ latestPrice, ticker }: Props) {
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [qty, setQty] = useState("");
  const [cost, setCost] = useState("");

  function addHolding() {
    const quantity = Number(qty);
    const avgCost = Number(cost);
    if (!quantity || !avgCost) return;
    setHoldings((prev) => [...prev, { ticker, quantity, avgCost }]);
    setQty("");
    setCost("");
  }

  const pnl = useMemo(() => {
    return holdings.reduce((acc, h) => acc + (latestPrice - h.avgCost) * h.quantity, 0);
  }, [holdings, latestPrice]);

  return (
    <section className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
      <h3 className="text-lg font-semibold text-slate-100">Portfolio Tracker</h3>
      <div className="mt-2 flex gap-2">
        <input
          value={qty}
          onChange={(e) => setQty(e.target.value)}
          placeholder="Qty"
          className="w-full rounded-md border border-slate-600 bg-slate-950 px-2 py-1 text-xs text-slate-100"
        />
        <input
          value={cost}
          onChange={(e) => setCost(e.target.value)}
          placeholder="Avg cost"
          className="w-full rounded-md border border-slate-600 bg-slate-950 px-2 py-1 text-xs text-slate-100"
        />
        <button onClick={addHolding} className="rounded-md bg-cyan-500 px-3 py-1 text-xs font-semibold text-slate-950">
          Add
        </button>
      </div>

      <p className={`mt-3 text-sm font-medium ${pnl >= 0 ? "text-emerald-300" : "text-rose-300"}`}>
        Unrealized P/L: {pnl.toFixed(2)} USD
      </p>
    </section>
  );
}
