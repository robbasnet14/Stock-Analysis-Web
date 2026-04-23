import { useEffect, useMemo, useState } from "react";
import { AuthPanel } from "../components/AuthPanel";
import { PortfolioChart } from "../components/charts/PortfolioChart";
import { RangePicker } from "../components/charts/RangePicker";
import { ChartCrosshair } from "../components/charts/ChartCrosshair";
import { TickerSearch } from "../components/portfolio/TickerSearch";
import { HoldingsTable } from "../components/portfolio/HoldingsTable";
import { usePortfolioSeries, ChartRange } from "../hooks/usePortfolioSeries";
import { useTickStream } from "../hooks/useTickStream";
import { getLiveStatus, getMarketSession, getPositions, me } from "../services/api";
import { isAuthenticated } from "../services/auth";
import { usePortfolioStore } from "../store/portfolio";
import { PricePoint, UserProfile } from "../types";

export default function Dashboard() {
  const [range, setRange] = useState<ChartRange>("1D");
  const [ticker, setTicker] = useState("AAPL");
  const [user, setUser] = useState<UserProfile | null>(null);
  const [hoverPoint, setHoverPoint] = useState<PricePoint | null>(null);
  const [providerConnected, setProviderConnected] = useState(false);
  const [sessionLabel, setSessionLabel] = useState("-");

  const holdings = usePortfolioStore((s) => s.holdings);
  const latestPrices = usePortfolioStore((s) => s.latestPrices);
  const setHoldings = usePortfolioStore((s) => s.setHoldings);

  const symbols = useMemo(() => {
    const fromHoldings = holdings.map((h) => h.ticker.toUpperCase());
    return fromHoldings.length ? fromHoldings : [ticker.toUpperCase()];
  }, [holdings, ticker]);

  useTickStream(symbols);

  const { series } = usePortfolioSeries({ range, ticker, holdings, latestPrices });

  const totals = useMemo(() => {
    if (!holdings.length) return { value: 0, cost: 0, pnl: 0, pct: 0 };
    const value = holdings.reduce((sum, h) => sum + (latestPrices[h.ticker]?.price || 0) * h.quantity, 0);
    const cost = holdings.reduce((sum, h) => sum + h.avg_cost * h.quantity, 0);
    const pnl = value - cost;
    const pct = cost > 0 ? (pnl / cost) * 100 : 0;
    return { value, cost, pnl, pct };
  }, [holdings, latestPrices]);

  const chartDelta = useMemo(() => {
    if (!series.length) return { delta: 0, pct: 0, active: 0 };
    const first = series[0].price;
    const active = hoverPoint?.price ?? series[series.length - 1].price;
    const delta = active - first;
    const pct = first > 0 ? (delta / first) * 100 : 0;
    return { delta, pct, active };
  }, [hoverPoint, series]);

  async function refreshAuth() {
    if (!isAuthenticated()) {
      setUser(null);
      setHoldings([]);
      return;
    }
    try {
      const [profile, pos] = await Promise.all([me(), getPositions()]);
      setUser(profile);
      setHoldings(pos);
    } catch {
      setUser(null);
      setHoldings([]);
    }
  }

  useEffect(() => {
    void refreshAuth();
    getLiveStatus()
      .then((s) => {
        const configured = s.providers_configured ? Object.values(s.providers_configured).some(Boolean) : Boolean(s.finnhub_configured);
        setProviderConnected(configured);
      })
      .catch(() => setProviderConnected(false));
    getMarketSession()
      .then((s) => setSessionLabel(`${s.session} · ${new Date(s.timestamp).toLocaleTimeString()}`))
      .catch(() => setSessionLabel("-"));
  }, [setHoldings]);

  return (
    <section className="space-y-4">
      <header className="rounded-xl border border-slate-300 bg-white/80 p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900/70">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-cyan-600 dark:text-cyan-300">AI Stock Analytics</p>
            <h1 className="text-3xl font-bold">Portfolio Home</h1>
            <p className="text-sm text-slate-600 dark:text-slate-300">A clean analytics-first home built for live market tracking.</p>
            <p className={`mt-2 inline-flex rounded-full px-2 py-1 text-xs font-semibold ${providerConnected ? "bg-emerald-500/20 text-emerald-500" : "bg-rose-500/20 text-rose-500"}`}>
              {providerConnected ? "Live market data connected" : "Live provider not connected"}
            </p>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Session: {sessionLabel}</p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <TickerSearch onSelect={setTicker} />
            <AuthPanel user={user} onAuthChange={refreshAuth} />
          </div>
        </div>
      </header>

      <section className="rounded-xl border border-slate-300 bg-white/80 p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900/70">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-sm text-slate-500 dark:text-slate-400">Total investing</p>
            <p className="text-4xl font-semibold">${totals.value.toFixed(2)}</p>
            <p className={`text-sm font-semibold ${totals.pnl >= 0 ? "text-emerald-500" : "text-rose-500"}`}>
              {totals.pnl >= 0 ? "+" : ""}${totals.pnl.toFixed(2)} ({totals.pct.toFixed(2)}%) total
            </p>
          </div>

          <div className="text-right">
            <p className="text-xs uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400">{holdings.length ? "Portfolio" : ticker}</p>
            <p className={`text-3xl font-semibold ${chartDelta.delta >= 0 ? "text-emerald-500" : "text-rose-500"}`}>${chartDelta.active.toFixed(2)}</p>
            <p className={`text-sm font-semibold ${chartDelta.delta >= 0 ? "text-emerald-500" : "text-rose-500"}`}>
              {chartDelta.delta >= 0 ? "+" : ""}${chartDelta.delta.toFixed(2)} ({chartDelta.pct.toFixed(2)}%)
            </p>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <RangePicker value={range} onChange={setRange} />
          <ChartCrosshair point={hoverPoint} />
        </div>

        <div className="mt-4">
          <PortfolioChart data={series} onHover={setHoverPoint} />
        </div>
      </section>

      <section className="rounded-xl border border-slate-300 bg-white/80 p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900/70">
        <h2 className="mb-3 text-lg font-semibold">Your Holdings</h2>
        <HoldingsTable holdings={holdings} latestPrices={latestPrices} onDelete={async () => undefined} />
      </section>
    </section>
  );
}
