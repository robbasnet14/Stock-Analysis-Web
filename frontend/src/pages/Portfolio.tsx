import { useEffect, useMemo, useState } from "react";
import { AuthPanel } from "../components/AuthPanel";
import { AddHoldingModal } from "../components/portfolio/AddHoldingModal";
import { CSVImport } from "../components/portfolio/CSVImport";
import { HoldingsTable } from "../components/portfolio/HoldingsTable";
import { TickerSearch } from "../components/portfolio/TickerSearch";
import { useTickStream } from "../hooks/useTickStream";
import { deleteHoldingLot, getHoldingLots, me, saveHoldingLot, updateHoldingLot } from "../services/api";
import { isAuthenticated } from "../services/auth";
import { usePortfolioStore } from "../store/portfolio";
import { Position, UserProfile } from "../types";

export default function Portfolio() {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [selectedTicker, setSelectedTicker] = useState("AAPL");
  const [editingHolding, setEditingHolding] = useState<Position | null>(null);

  const holdings = usePortfolioStore((s) => s.holdings);
  const latestPrices = usePortfolioStore((s) => s.latestPrices);
  const setHoldings = usePortfolioStore((s) => s.setHoldings);

  const symbols = useMemo(() => Array.from(new Set(holdings.map((h) => h.ticker))), [holdings]);
  useTickStream(symbols);

  async function refresh() {
    if (!isAuthenticated()) {
      setUser(null);
      setHoldings([]);
      return;
    }
    try {
      const [profile, positions] = await Promise.all([me(), getHoldingLots()]);
      setUser(profile);
      setHoldings(positions);
    } catch {
      setUser(null);
      setHoldings([]);
    }
  }

  async function triggerDashboardRefresh() {
    window.dispatchEvent(new CustomEvent("portfolio-updated"));
  }

  async function handleSaveHolding(input: {
    lotId?: number;
    ticker: string;
    shares: number;
    buyPrice: number;
    buyTs?: string;
    mergeMode?: "ask" | "merge" | "new_lot";
  }) {
    if (typeof input.lotId === "number") {
      await updateHoldingLot(input.lotId, {
        shares: input.shares,
        buy_price: input.buyPrice,
        buy_ts: input.buyTs
      });
    } else {
      await saveHoldingLot(input.ticker, input.shares, input.buyPrice, input.buyTs, input.mergeMode ?? "ask");
    }
    await refresh();
    await triggerDashboardRefresh();
  }

  async function handleDeleteHolding(id: number) {
    await deleteHoldingLot(id);
    await refresh();
    await triggerDashboardRefresh();
  }

  function onEditClosed() {
    setEditingHolding(null);
  }

  useEffect(() => {
    void refresh();
  }, [setHoldings]);

  const totals = useMemo(() => {
    const market = holdings.reduce((sum, h) => sum + (latestPrices[h.ticker]?.price || 0) * h.quantity, 0);
    const cost = holdings.reduce((sum, h) => sum + h.avg_cost * h.quantity, 0);
    const pnl = market - cost;
    return { market, cost, pnl };
  }, [holdings, latestPrices]);

  return (
    <section className="space-y-4">
      <header className="rounded-xl border border-slate-300 bg-white/80 p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900/70">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold">Portfolio Builder</h1>
            <p className="text-sm text-slate-600 dark:text-slate-300">Add real holdings, watch live P/L, and import Robinhood-style CSV quickly.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <TickerSearch onSelect={setSelectedTicker} />
            <AuthPanel user={user} onAuthChange={refresh} />
          </div>
        </div>
      </header>

      {!user ? (
        <div className="rounded-xl border border-slate-300 bg-white/80 p-4 text-sm dark:border-slate-700 dark:bg-slate-900/70">
          Sign in to manage your portfolio.
        </div>
      ) : (
        <>
          <section className="grid gap-4 md:grid-cols-[2fr_1fr]">
            <div className="rounded-xl border border-slate-300 bg-white/80 p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900/70">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-lg font-semibold">Holdings</h2>
                <AddHoldingModal initialTicker={selectedTicker} editRow={editingHolding} onEditClosed={onEditClosed} onSubmit={handleSaveHolding} />
              </div>
              <HoldingsTable holdings={holdings} latestPrices={latestPrices} onEdit={(row) => setEditingHolding(row)} onDelete={handleDeleteHolding} />
            </div>

            <div className="space-y-4">
              <CSVImport onDone={refresh} />
              <div className="rounded-xl border border-slate-300 bg-white/80 p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900/70">
                <h3 className="text-sm font-semibold">Portfolio Totals</h3>
                <p className="mt-2 text-sm">Market value: ${totals.market.toFixed(2)}</p>
                <p className="text-sm">Cost basis: ${totals.cost.toFixed(2)}</p>
                <p className={`text-sm font-semibold ${totals.pnl >= 0 ? "text-emerald-500" : "text-rose-500"}`}>
                  P/L: {totals.pnl >= 0 ? "+" : ""}${totals.pnl.toFixed(2)}
                </p>
              </div>
            </div>
          </section>
        </>
      )}
    </section>
  );
}
