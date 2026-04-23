import { useEffect, useMemo, useState } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { TickerSearch } from "../components/portfolio/TickerSearch";
import { EnsembleTrack, EnsembleRow } from "../components/signals/EnsembleTrack";
import { TechnicalTrack, TechnicalRow } from "../components/signals/TechnicalTrack";
import { getHoldingLots, getSignalBatch, getWatchlist } from "../services/api";
import { usePortfolioStore } from "../store/portfolio";

const HORIZONS = ["short", "mid", "long"] as const;
const FALLBACK_TICKERS = ["AAPL", "BTC-USD", "ETH-USD"];
const SIGNALS_SCROLL_KEY = "signals:return";

export default function Signals() {
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialTrack = searchParams.get("track") === "ensemble" ? "ensemble" : "technical";
  const initialHorizon = HORIZONS.includes((searchParams.get("horizon") as (typeof HORIZONS)[number]) ?? "short")
    ? ((searchParams.get("horizon") as (typeof HORIZONS)[number]) ?? "short")
    : "short";

  const [tab, setTab] = useState<"technical" | "ensemble">(initialTrack);
  const [horizon, setHorizon] = useState<(typeof HORIZONS)[number]>(initialHorizon);
  const [technicalRows, setTechnicalRows] = useState<TechnicalRow[]>([]);
  const [ensembleRows, setEnsembleRows] = useState<EnsembleRow[]>([]);

  const signalTickers = usePortfolioStore((s) => s.signalTickers);
  const setSignalTickers = usePortfolioStore((s) => s.setSignalTickers);
  const addSignalTicker = usePortfolioStore((s) => s.addSignalTicker);
  const removeSignalTicker = usePortfolioStore((s) => s.removeSignalTicker);

  useEffect(() => {
    const next = new URLSearchParams(searchParams);
    next.set("track", tab);
    next.set("horizon", horizon);
    setSearchParams(next, { replace: true });
  }, [horizon, searchParams, setSearchParams, tab]);

  useEffect(() => {
    const stored = sessionStorage.getItem(SIGNALS_SCROLL_KEY);
    if (!stored) return;
    try {
      const parsed = JSON.parse(stored) as { scrollY?: number; track?: "technical" | "ensemble"; horizon?: (typeof HORIZONS)[number] };
      if (parsed.track) setTab(parsed.track);
      if (parsed.horizon && HORIZONS.includes(parsed.horizon)) setHorizon(parsed.horizon);
      window.requestAnimationFrame(() => {
        window.scrollTo({ top: Number(parsed.scrollY) || 0, behavior: "auto" });
      });
    } catch {
      // Ignore corrupted state.
    }
    sessionStorage.removeItem(SIGNALS_SCROLL_KEY);
  }, [location.key]);

  useEffect(() => {
    let mounted = true;

    const initTickers = async () => {
      if (signalTickers.length) return;
      try {
        const [holdings, watchlist] = await Promise.all([getHoldingLots(), getWatchlist()]);
        const fromHoldings = holdings.map((h) => h.ticker.toUpperCase());
        const merged = Array.from(new Set([...fromHoldings, ...watchlist.map((w) => w.toUpperCase())]));
        const defaults = merged.length ? merged : FALLBACK_TICKERS;
        if (mounted) setSignalTickers(defaults);
      } catch {
        if (mounted) setSignalTickers(FALLBACK_TICKERS);
      }
    };

    void initTickers();
    return () => {
      mounted = false;
    };
  }, [setSignalTickers, signalTickers.length]);

  useEffect(() => {
    let mounted = true;

    const load = async () => {
      if (!signalTickers.length) {
        setTechnicalRows([]);
        setEnsembleRows([]);
        return;
      }
      try {
        if (tab === "technical") {
          const rows = await getSignalBatch("technical", horizon, signalTickers);
          if (mounted) setTechnicalRows(rows as TechnicalRow[]);
        } else {
          const rows = await getSignalBatch("ensemble", horizon, signalTickers);
          if (mounted) setEnsembleRows(rows as EnsembleRow[]);
        }
      } catch {
        if (!mounted) return;
        setTechnicalRows([]);
        setEnsembleRows([]);
      }
    };

    void load();

    return () => {
      mounted = false;
    };
  }, [horizon, signalTickers, tab]);

  const chips = useMemo(() => signalTickers, [signalTickers]);
  const hrefForTicker = (ticker: string) => `/signals/${encodeURIComponent(ticker)}?horizon=${encodeURIComponent(horizon)}`;
  const handleOpenTicker = (_ticker: string) => {
    sessionStorage.setItem(
      SIGNALS_SCROLL_KEY,
      JSON.stringify({
        scrollY: window.scrollY,
        track: tab,
        horizon
      })
    );
  };

  return (
    <section className="space-y-4">
      <header className="rounded-xl border border-slate-300 bg-white/80 p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900/70">
        <h1 className="text-2xl font-bold">Signal Tracks</h1>
        <p className="text-sm text-slate-600 dark:text-slate-300">Switch between technical and ensemble tracks across short/mid/long horizons.</p>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setTab("technical")}
            className={`rounded-full px-3 py-1 text-xs font-semibold ${tab === "technical" ? "bg-cyan-500 text-slate-950" : "bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300"}`}
          >
            Technical
          </button>
          <button
            type="button"
            onClick={() => setTab("ensemble")}
            className={`rounded-full px-3 py-1 text-xs font-semibold ${tab === "ensemble" ? "bg-cyan-500 text-slate-950" : "bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300"}`}
          >
            Ensemble
          </button>

          <span className="mx-1 text-xs text-slate-400">|</span>

          {HORIZONS.map((h) => (
            <button
              key={h}
              type="button"
              onClick={() => setHorizon(h)}
              className={`rounded-full px-3 py-1 text-xs font-semibold ${horizon === h ? "bg-slate-900 text-slate-100 dark:bg-slate-100 dark:text-slate-900" : "bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300"}`}
            >
              {h}
            </button>
          ))}
        </div>

        <div className="mt-4 max-w-md">
          <TickerSearch onSelect={(symbol) => addSignalTicker(symbol)} />
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          {chips.map((ticker) => (
            <span key={ticker} className="inline-flex items-center gap-2 rounded-full border border-slate-300 bg-slate-100 px-3 py-1 text-xs dark:border-slate-700 dark:bg-slate-800">
              {ticker}
              <button
                type="button"
                onClick={() => removeSignalTicker(ticker)}
                className="rounded-full px-1 text-[10px] text-slate-500 hover:bg-slate-300 hover:text-slate-900 dark:hover:bg-slate-700 dark:hover:text-slate-100"
                aria-label={`Remove ${ticker}`}
              >
                X
              </button>
            </span>
          ))}
        </div>
      </header>

      {tab === "technical" ? (
        <TechnicalTrack items={technicalRows} hrefForTicker={hrefForTicker} onOpenTicker={handleOpenTicker} />
      ) : (
        <EnsembleTrack items={ensembleRows} hrefForTicker={hrefForTicker} onOpenTicker={handleOpenTicker} />
      )}
    </section>
  );
}
