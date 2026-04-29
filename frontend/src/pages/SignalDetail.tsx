import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, ExternalLink, Info, Plus, TrendingDown, TrendingUp } from "lucide-react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { BaselineSeries, ColorType, createChart, LineStyle } from "lightweight-charts";
import { getHoldingLots, getSignalDetail, saveHoldingLot } from "../services/api";
import { isAuthenticated } from "../services/auth";
import { usePortfolioStore } from "../store/portfolio";
import { SignalDetailResponse } from "../types";

const HORIZONS = ["short", "mid", "long"] as const;
const TRACKS = ["technical", "ensemble"] as const;
const SIGNALS_SCROLL_KEY = "signals:return";

function classForVerdict(label: string) {
  if (label === "BULLISH") return "border-emerald-400/50 bg-emerald-500/10 text-emerald-300";
  if (label === "BEARISH") return "border-rose-400/50 bg-rose-500/10 text-rose-300";
  return "border-slate-600 bg-slate-800/80 text-slate-200";
}

function pct(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "Insufficient history";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function currency(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "Insufficient history";
  return `$${value.toFixed(2)}`;
}

function MiniChart({ bars, support, resistance }: { bars: SignalDetailResponse["mini_chart_bars"]; support: number; resistance: number }) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!containerRef.current || !bars.length) return;

    const chart = createChart(containerRef.current, {
      autoSize: true,
      height: window.innerWidth < 640 ? 150 : 220,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#94a3b8"
      },
      grid: {
        vertLines: { color: "rgba(51, 65, 85, 0.35)" },
        horzLines: { color: "rgba(51, 65, 85, 0.35)" }
      },
      rightPriceScale: {
        borderColor: "rgba(51, 65, 85, 0.5)"
      },
      timeScale: {
        borderColor: "rgba(51, 65, 85, 0.5)"
      },
      crosshair: {
        vertLine: { visible: false, labelVisible: false },
        horzLine: { visible: false, labelVisible: false }
      }
    });

    const series = chart.addSeries(BaselineSeries, {
      baseValue: { type: "price", price: bars[0]?.close ?? 0 },
      topLineColor: "#22c55e",
      topFillColor1: "rgba(34, 197, 94, 0.25)",
      topFillColor2: "rgba(34, 197, 94, 0.02)",
      bottomLineColor: "#f43f5e",
      bottomFillColor1: "rgba(244, 63, 94, 0.14)",
      bottomFillColor2: "rgba(244, 63, 94, 0.02)",
      lineWidth: 2,
      crosshairMarkerVisible: false
    });
    series.setData(
      bars.map((bar) => ({
        time: bar.timestamp.slice(0, 10),
        value: bar.close
      }))
    );

    const supportLine = series.createPriceLine({
      price: support,
      color: "#38bdf8",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: true,
      title: "Support"
    });
    const resistanceLine = series.createPriceLine({
      price: resistance,
      color: "#f59e0b",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: true,
      title: "Resistance"
    });

    chart.timeScale().fitContent();
    return () => {
      series.removePriceLine(supportLine);
      series.removePriceLine(resistanceLine);
      chart.remove();
    };
  }, [bars, resistance, support]);

  return <div ref={containerRef} className="h-[150px] sm:h-[220px]" />;
}

export default function SignalDetail() {
  const { ticker = "" } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const horizonParam = searchParams.get("horizon");
  const horizon = HORIZONS.includes((horizonParam as (typeof HORIZONS)[number]) ?? "short") ? ((horizonParam as (typeof HORIZONS)[number]) ?? "short") : "short";

  const [track, setTrack] = useState<"technical" | "ensemble">("ensemble");
  const [detail, setDetail] = useState<SignalDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState("");

  const holdings = usePortfolioStore((s) => s.holdings);
  const setHoldings = usePortfolioStore((s) => s.setHoldings);
  const alreadyHeld = useMemo(() => holdings.some((row) => row.ticker.toUpperCase() === ticker.toUpperCase()), [holdings, ticker]);

  useEffect(() => {
    if (!isAuthenticated()) {
      setHoldings([]);
      return;
    }
    void getHoldingLots().then(setHoldings).catch(() => undefined);
  }, [setHoldings]);

  useEffect(() => {
    const trackParam = searchParams.get("track");
    setTrack(trackParam === "technical" ? "technical" : "ensemble");
  }, [searchParams]);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setError("");
    void getSignalDetail(ticker, horizon)
      .then((response) => {
        if (!mounted) return;
        setDetail(response);
      })
      .catch((err: unknown) => {
        if (!mounted) return;
        setError(err instanceof Error ? err.message : "Unable to load signal detail.");
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [horizon, ticker]);

  const activeSignal = detail?.signals[track];
  const activeVerdict = activeSignal?.verdict ?? detail?.verdict;
  const rules = activeSignal?.triggered_rules ?? detail?.triggered_rules ?? [];
  const weightedSum = rules.reduce((sum, row) => sum + row.vote * row.weight, 0);
  const insufficientHistory = Boolean(detail && detail.projection.sample_size < 20);

  async function handleAddToPortfolio() {
    if (!detail || alreadyHeld || saving) return;
    setSaving(true);
    setSaveMessage("");
    try {
      await saveHoldingLot(detail.ticker, 1, detail.quote.price, undefined, "new_lot");
      const lots = await getHoldingLots();
      setHoldings(lots);
      setSaveMessage("Added 1 share at the current price.");
    } catch (err) {
      setSaveMessage(err instanceof Error ? err.message : "Unable to add this ticker right now.");
    } finally {
      setSaving(false);
    }
  }

  function handleBack() {
    const stored = sessionStorage.getItem(SIGNALS_SCROLL_KEY);
    if (stored) {
      try {
        const parsed = JSON.parse(stored) as { track?: "technical" | "ensemble"; horizon?: string };
        navigate(`/signals?track=${encodeURIComponent(parsed.track ?? "technical")}&horizon=${encodeURIComponent(parsed.horizon ?? "short")}`);
        return;
      } catch {
        // fall through
      }
    }
    navigate(`/signals?track=${encodeURIComponent(track)}&horizon=${encodeURIComponent(horizon)}`);
  }

  function updateHorizon(next: (typeof HORIZONS)[number]) {
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("horizon", next);
    nextParams.set("track", track);
    setSearchParams(nextParams, { replace: true });
  }

  function updateTrack(next: "technical" | "ensemble") {
    setTrack(next);
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("horizon", horizon);
    nextParams.set("track", next);
    setSearchParams(nextParams, { replace: true });
  }

  if (loading) {
    return <div className="rounded-xl border border-slate-700 bg-slate-900/80 p-6 text-sm text-slate-300">Loading signal detail...</div>;
  }

  if (!detail || error) {
    return (
      <div className="rounded-xl border border-rose-500/40 bg-slate-900/80 p-6 text-sm text-rose-200">
        <button type="button" onClick={handleBack} className="mb-4 inline-flex items-center gap-2 rounded-full border border-slate-700 px-3 py-1 text-slate-200">
          <ArrowLeft size={14} />
          Back to signals
        </button>
        {error || "Signal detail unavailable."}
      </div>
    );
  }

  return (
    <section className="space-y-4">
      <header className="rounded-2xl border border-slate-700 bg-slate-900/80 p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-2">
            <button type="button" onClick={handleBack} className="inline-flex items-center gap-2 rounded-full border border-slate-700 px-3 py-1 text-sm text-slate-300 hover:border-slate-500 hover:text-white">
              <ArrowLeft size={14} />
              Back to signals
            </button>
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-cyan-300/70">{detail.asset_class}</p>
              <h1 className="text-3xl font-bold text-white">{detail.ticker}</h1>
              <p className="text-sm text-slate-400">{detail.company_name}</p>
            </div>
            <div className="flex flex-wrap items-end gap-3">
              <p className="text-4xl font-semibold text-white">${detail.quote.price.toFixed(2)}</p>
              <p className={`pb-1 text-sm font-semibold ${detail.quote.change >= 0 ? "text-emerald-300" : "text-rose-300"}`}>
                {detail.quote.change >= 0 ? "+" : ""}{detail.quote.change.toFixed(2)} ({detail.quote.change_percent >= 0 ? "+" : ""}{detail.quote.change_percent.toFixed(2)}%)
              </p>
            </div>
          </div>

          <div className="flex w-full max-w-md flex-col items-stretch gap-3">
            {alreadyHeld ? (
              <div className="rounded-xl border border-emerald-400/40 bg-emerald-500/10 px-4 py-3 text-sm font-semibold text-emerald-300">Already in portfolio</div>
            ) : (
              <button
                type="button"
                onClick={() => void handleAddToPortfolio()}
                disabled={saving}
                className="inline-flex items-center justify-center gap-2 rounded-xl bg-cyan-400 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-70"
              >
                <Plus size={16} />
                {saving ? "Adding..." : "Add to portfolio"}
              </button>
            )}
            {saveMessage ? <p className="text-xs text-slate-400">{saveMessage}</p> : null}

            <div className="flex flex-wrap gap-2">
              {HORIZONS.map((value) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => updateHorizon(value)}
                  className={`rounded-full px-3 py-1.5 text-xs font-semibold uppercase tracking-wide ${horizon === value ? "bg-cyan-400 text-slate-950" : "bg-slate-800 text-slate-300"}`}
                >
                  {value}
                </button>
              ))}
            </div>

            <div className="flex flex-wrap gap-2">
              {TRACKS.map((value) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => updateTrack(value)}
                  className={`rounded-full px-3 py-1.5 text-xs font-semibold ${track === value ? "bg-white text-slate-950" : "bg-slate-800 text-slate-300"}`}
                >
                  {value === "technical" ? "Technical" : "Ensemble"}
                </button>
              ))}
            </div>
          </div>
        </div>
      </header>

      <section className="grid gap-4 xl:grid-cols-[1.25fr_0.95fr]">
        <div className="space-y-4">
          <div className={`rounded-2xl border p-5 shadow-sm ${classForVerdict(activeVerdict?.label ?? "NEUTRAL")}`}>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Verdict</p>
                <p className="mt-2 text-4xl font-black">{activeVerdict?.label}</p>
                <p className="mt-2 text-sm text-slate-300">{activeSignal?.explanation}</p>
              </div>
              <div className="min-w-[200px] space-y-3">
                <div>
                  <div className="mb-1 flex items-center justify-between text-xs text-slate-300">
                    <span>Confidence</span>
                    <span>{activeVerdict?.confidence ?? 0}%</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-slate-950/50">
                    <div className={`h-full rounded-full ${activeVerdict?.label === "BULLISH" ? "bg-emerald-400" : activeVerdict?.label === "BEARISH" ? "bg-rose-400" : "bg-slate-400"}`} style={{ width: `${Math.max(0, Math.min(100, activeVerdict?.confidence ?? 0))}%` }} />
                  </div>
                </div>
                <div>
                  <div className="mb-2 flex items-center justify-between text-xs text-slate-300">
                    <span>Score</span>
                    <span>{(activeVerdict?.score ?? 0).toFixed(2)}</span>
                  </div>
                  <div className="relative h-3 rounded-full bg-slate-950/50">
                    <div className="absolute inset-y-0 left-1/2 w-px bg-slate-500/60" />
                    <div
                      className={`absolute top-0 h-3 rounded-full ${(activeVerdict?.score ?? 0) >= 0 ? "bg-emerald-400" : "bg-rose-400"}`}
                      style={{
                        left: `${Math.min(50, ((activeVerdict?.score ?? 0) + 1) * 50)}%`,
                        width: "8px",
                        transform: "translateX(-50%)"
                      }}
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-700 bg-slate-900/80 p-5 shadow-sm">
            <div className="flex items-center justify-between gap-2">
              <div>
                <h2 className="text-lg font-semibold text-white">Projection</h2>
                <p className="text-sm text-slate-400">Historical outcomes for similar {detail.horizon} setups.</p>
              </div>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-3">
              {[
                {
                  label: "Bearish case",
                  price: detail.projection.projected_price_bear,
                  pctValue: detail.projection.bearish_case_pct,
                  tone: "text-rose-300",
                  icon: <TrendingDown size={16} />
                },
                {
                  label: "Median",
                  price: detail.projection.projected_price_median,
                  pctValue: detail.projection.median_return_pct,
                  tone: "text-cyan-300",
                  icon: <Info size={16} />
                },
                {
                  label: "Bullish case",
                  price: detail.projection.projected_price_bull,
                  pctValue: detail.projection.bullish_case_pct,
                  tone: "text-emerald-300",
                  icon: <TrendingUp size={16} />
                }
              ].map((item) => (
                <div key={item.label} className="rounded-xl border border-slate-700 bg-slate-950/70 p-4">
                  <div className={`flex items-center gap-2 text-sm font-semibold ${item.tone}`}>{item.icon}{item.label}</div>
                  <p className="mt-3 text-2xl font-semibold text-white">{currency(item.price)}</p>
                  <p className={`mt-1 text-sm ${item.tone}`}>{pct(item.pctValue)}</p>
                </div>
              ))}
            </div>
            <div className="mt-4 text-sm text-slate-300">
              {insufficientHistory ? (
                <p>Limited historical data for this setup. Sample size: {detail.projection.sample_size}.</p>
              ) : (
                <p>Past accuracy: {detail.projection.accuracy_pct}% ({detail.projection.sample_size} similar setups since {detail.projection.backtest_start?.slice(0, 4) ?? "N/A"})</p>
              )}
            </div>
          </div>

          <div className="rounded-2xl border border-slate-700 bg-slate-900/80 p-5 shadow-sm">
            <div className="mb-4 flex items-center justify-between gap-2">
              <div>
                <h2 className="text-lg font-semibold text-white">Triggered Rules</h2>
                <p className="text-sm text-slate-400">Driver breakdown for the active {track} track.</p>
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="pb-3 pr-4">Rule</th>
                    <th className="pb-3 pr-4">Value</th>
                    <th className="pb-3 pr-4">Vote</th>
                    <th className="pb-3 pr-4">Weight</th>
                    <th className="pb-3 pr-4">Contribution</th>
                  </tr>
                </thead>
                <tbody>
                  {rules.map((rule) => (
                    <tr key={rule.rule} className="border-t border-slate-800 text-slate-200">
                      <td className="py-3 pr-4">
                        <div className="flex items-center gap-2">
                          <span>{rule.rule}</span>
                          <span title={rule.explanation} className="text-slate-500">
                            <Info size={14} />
                          </span>
                        </div>
                      </td>
                      <td className="py-3 pr-4">{rule.value.toFixed(2)}</td>
                      <td className={`py-3 pr-4 font-semibold ${rule.vote > 0 ? "text-emerald-300" : rule.vote < 0 ? "text-rose-300" : "text-slate-400"}`}>{rule.vote > 0 ? "+1" : rule.vote < 0 ? "-1" : "0"}</td>
                      <td className="py-3 pr-4">{rule.weight.toFixed(2)}</td>
                      <td className={`py-3 pr-4 font-semibold ${(rule.vote * rule.weight) >= 0 ? "text-emerald-300" : "text-rose-300"}`}>{(rule.vote * rule.weight) >= 0 ? "+" : ""}{(rule.vote * rule.weight).toFixed(2)}</td>
                    </tr>
                  ))}
                  <tr className="border-t border-slate-700 font-semibold text-white">
                    <td className="py-3 pr-4">Weighted sum</td>
                    <td className="py-3 pr-4" />
                    <td className="py-3 pr-4" />
                    <td className="py-3 pr-4" />
                    <td className={`${weightedSum >= 0 ? "text-emerald-300" : "text-rose-300"} py-3 pr-4`}>{weightedSum >= 0 ? "+" : ""}{weightedSum.toFixed(2)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-2xl border border-slate-700 bg-slate-900/80 p-5 shadow-sm">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-white">Context</h2>
                <p className="text-sm text-slate-400">Market, sector, event, and theme filters.</p>
              </div>
              <span className="rounded-full border border-slate-700 px-2 py-1 text-xs font-semibold uppercase text-slate-300">
                {detail.context?.regime ?? "unknown"}
              </span>
            </div>
            <div className="mt-4 grid gap-3 text-sm">
              <div className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-2 text-slate-300">
                <span>Regime</span>
                <span className="font-semibold text-white">
                  SPY {detail.context?.regime_context?.spy_above_200ema ? "above" : "below"} 200-EMA · VIX {(detail.context?.regime_context?.vix ?? 0).toFixed(1)}
                </span>
              </div>
              <div className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-2 text-slate-300">
                <span>Sector</span>
                <span className={`font-semibold ${detail.context?.sector_position === "leading" ? "text-emerald-300" : detail.context?.sector_position === "lagging" ? "text-rose-300" : "text-slate-200"}`}>
                  {detail.context?.sector ?? "unknown"} · {detail.context?.sector_position ?? "neutral"}
                </span>
              </div>
              <div className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-2 text-slate-300">
                <span>Earnings</span>
                <span className="font-semibold text-white">
                  {detail.context?.next_earnings?.date ? `${detail.context.next_earnings.date}${detail.context.next_earnings.hour ? ` · ${detail.context.next_earnings.hour}` : ""}` : "No event in next 60 days"}
                </span>
              </div>
              <div className="rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-2 text-slate-300">
                <div className="flex items-center justify-between gap-3">
                  <span>Themes</span>
                  <span className="font-semibold text-white">
                    {detail.context?.matched_themes?.length ? detail.context.matched_themes.map((t) => t.theme).join(", ") : "No hot theme match"}
                  </span>
                </div>
              </div>
            </div>
            {detail.context?.extras?.length ? (
              <div className="mt-4 space-y-2">
                {detail.context.extras.map((item) => (
                  <p key={item} className="rounded-xl border border-cyan-400/20 bg-cyan-500/10 px-3 py-2 text-sm text-cyan-100">{item}</p>
                ))}
              </div>
            ) : null}
          </div>

          <div className="rounded-2xl border border-slate-700 bg-slate-900/80 p-5 shadow-sm">
            <div className="flex items-center justify-between gap-2">
              <div>
                <h2 className="text-lg font-semibold text-white">News Context</h2>
                <p className="text-sm text-slate-400">{detail.news.article_count_24h} articles in the last 24 hours</p>
              </div>
              <div className="text-right">
                <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Sentiment</p>
                <p className={`text-2xl font-semibold ${detail.news.sentiment_score >= 0 ? "text-emerald-300" : "text-rose-300"}`}>{detail.news.sentiment_score.toFixed(2)}</p>
              </div>
            </div>
            <div className="mt-4 space-y-3">
              {detail.news.top_articles.map((article) => (
                <a key={`${article.url}-${article.published_at}`} href={article.url || "#"} target="_blank" rel="noreferrer" className="block rounded-xl border border-slate-800 bg-slate-950/70 p-3 hover:border-slate-600">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-medium text-white">{article.title}</p>
                      <p className="mt-1 text-xs text-slate-400">{article.source} · {new Date(article.published_at).toLocaleString()}</p>
                    </div>
                    <span className="inline-flex items-center gap-1 rounded-full border border-slate-700 px-2 py-1 text-[11px] text-slate-300">
                      {article.sentiment}
                      <ExternalLink size={12} />
                    </span>
                  </div>
                </a>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-slate-700 bg-slate-900/80 p-5 shadow-sm">
            <h2 className="text-lg font-semibold text-white">Key Levels</h2>
            <div className="mt-4 space-y-3 text-sm">
              <div className="flex items-center justify-between text-slate-300"><span>Current</span><span className="font-semibold text-white">${detail.levels.current.toFixed(2)}</span></div>
              <div className="flex items-center justify-between text-slate-300"><span>Support</span><span>${detail.levels.support.toFixed(2)}</span></div>
              <div className="flex items-center justify-between text-slate-300"><span>Resistance</span><span>${detail.levels.resistance.toFixed(2)}</span></div>
              <div className="flex items-center justify-between text-rose-300"><span>Suggested stop</span><span>${detail.levels.suggested_stop.toFixed(2)}</span></div>
              <div className="flex items-center justify-between text-emerald-300"><span>Take profit</span><span>${detail.levels.suggested_take_profit.toFixed(2)}</span></div>
              <div className="rounded-xl border border-cyan-400/30 bg-cyan-500/10 px-3 py-3 text-cyan-200">
                Risk/Reward ratio: <span className="font-semibold">{detail.levels.risk_reward_ratio.toFixed(2)}</span>
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-700 bg-slate-900/80 p-5 shadow-sm">
            <h2 className="text-lg font-semibold text-white">Mini-chart</h2>
            <p className="text-sm text-slate-400">Last 30 trading days with support and resistance.</p>
            <div className="mt-4">
              <MiniChart bars={detail.mini_chart_bars} support={detail.levels.support} resistance={detail.levels.resistance} />
            </div>
          </div>
        </div>
      </section>

      <footer className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4 text-xs text-slate-500">
        Analysis based on technical indicators and historical patterns. Not financial advice. Past performance does not guarantee future results. Backtest period: {detail.projection.backtest_start ?? "N/A"} to {detail.projection.backtest_end ?? "N/A"}.
      </footer>
    </section>
  );
}
