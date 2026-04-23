import { useEffect, useMemo, useState } from "react";
import { getCandles, getPortfolioHistory, getPortfolioValueHistory } from "../services/api";
import { isAuthenticated } from "../services/auth";
import { Position, PricePoint } from "../types";
import { LatestPrice } from "../store/portfolio";

export type ChartRange = "1D" | "1W" | "1M" | "3M" | "1Y" | "ALL";

function toBackendRange(range: ChartRange): "1D" | "1W" | "1M" | "1Y" {
  if (range === "3M") return "1M";
  if (range === "ALL") return "1Y";
  return range;
}

type UsePortfolioSeriesArgs = {
  range: ChartRange;
  ticker: string;
  holdings: Position[];
  latestPrices: Record<string, LatestPrice>;
};

export function usePortfolioSeries({ range, ticker, holdings, latestPrices }: UsePortfolioSeriesArgs) {
  const [series, setSeries] = useState<PricePoint[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let mounted = true;
    const backendRange = toBackendRange(range);

    const load = async () => {
      setLoading(true);
      try {
        if (isAuthenticated() && holdings.length > 0) {
          const [snapshots, fallback] = await Promise.all([
            getPortfolioHistory(backendRange),
            getPortfolioValueHistory(backendRange)
          ]);
          const rows = snapshots.length ? snapshots : fallback;
          if (mounted && rows.length) {
            setSeries(rows);
            return;
          }
        }

        const stockRows = await getCandles(ticker, backendRange);
        if (mounted) {
          setSeries(stockRows);
        }
      } catch {
        if (mounted) setSeries([]);
      } finally {
        if (mounted) setLoading(false);
      }
    };

    void load();

    return () => {
      mounted = false;
    };
  }, [holdings.length, range, ticker]);

  const liveValue = useMemo(() => {
    if (!holdings.length) return 0;
    return holdings.reduce((sum, h) => sum + (latestPrices[h.ticker]?.price || 0) * h.quantity, 0);
  }, [holdings, latestPrices]);

  const adjustedSeries = useMemo(() => {
    if (!holdings.length || !series.length) return series;
    const cloned = [...series];
    const last = cloned[cloned.length - 1];
    if (liveValue > 0 && last) {
      cloned[cloned.length - 1] = {
        ...last,
        price: liveValue,
        open_price: liveValue,
        high_price: Math.max(last.high_price, liveValue),
        low_price: Math.min(last.low_price, liveValue)
      };
    }
    return cloned;
  }, [holdings.length, liveValue, series]);

  return {
    series: adjustedSeries,
    loading
  };
}
