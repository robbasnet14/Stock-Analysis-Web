import { useEffect, useMemo, useRef, useState } from "react";
import { createStockSocket } from "../services/websocket";
import { getCandles, getLatestStock, getPrediction } from "../services/api";
import { Prediction, PricePoint, StockTick } from "../types";

function minuteBucket(timestamp: string | Date): string {
  const dt = new Date(timestamp);
  dt.setSeconds(0, 0);
  return dt.toISOString();
}

function upsertFromTick(prev: PricePoint[], tick: StockTick, range: "1D" | "1W" | "1M" | "1Y"): PricePoint[] {
  const price = Number(tick.price);
  if (!Number.isFinite(price) || price <= 0) return prev;

  const tickPoint: PricePoint = {
    price,
    volume: Number(tick.volume || 0),
    change_percent: Number(tick.change_percent || 0),
    open_price: price,
    high_price: price,
    low_price: price,
    timestamp: tick.timestamp,
  };

  if (!prev.length) return [tickPoint];

  // For 1D we maintain minute candles to avoid day-high/day-low spike wicks from quote payloads.
  if (range === "1D") {
    const bucket = minuteBucket(tick.timestamp);
    const last = prev[prev.length - 1];
    const lastBucket = minuteBucket(last.timestamp);
    if (bucket === lastBucket) {
      const open = Number(last.open_price ?? last.price);
      const high = Math.max(Number(last.high_price ?? last.price), price);
      const low = Math.min(Number(last.low_price ?? last.price), price);
      const merged: PricePoint = {
        ...last,
        price,
        volume: Number(last.volume || 0) + Number(tick.volume || 0),
        open_price: open,
        high_price: high,
        low_price: low,
        timestamp: tick.timestamp,
      };
      return [...prev.slice(0, -1), merged];
    }
    return [...prev.slice(-359), tickPoint];
  }

  // For wider ranges, update most recent candle close with live quote.
  const last = prev[prev.length - 1];
  const open = Number(last.open_price ?? last.price);
  const high = Math.max(Number(last.high_price ?? last.price), price);
  const low = Math.min(Number(last.low_price ?? last.price), price);
  const merged: PricePoint = {
    ...last,
    price,
    volume: Number(last.volume || 0) + Number(tick.volume || 0),
    open_price: open,
    high_price: high,
    low_price: low,
    timestamp: tick.timestamp,
  };
  return [...prev.slice(0, -1), merged];
}

export function useStockStream(ticker: string, range: "1D" | "1W" | "1M" | "1Y") {
  const [latest, setLatest] = useState<StockTick | null>(null);
  const [history, setHistory] = useState<PricePoint[]>([]);
  const [prediction, setPrediction] = useState<Prediction | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let mounted = true;

    async function bootstrap() {
      setLoading(true);
      setError("");
      try {
        const [latestResp, historyResp, predictionResp] = await Promise.allSettled([
          getLatestStock(ticker),
          getCandles(ticker, range),
          getPrediction(ticker)
        ]);

        if (!mounted) return;
        if (latestResp.status === "fulfilled") {
          setLatest(latestResp.value);
        }
        if (historyResp.status === "fulfilled") {
          setHistory(historyResp.value);
        }
        if (predictionResp.status === "fulfilled") {
          setPrediction(predictionResp.value);
        }

        const messages: string[] = [];
        if (latestResp.status === "rejected") messages.push("Live quote unavailable");
        if (historyResp.status === "rejected") messages.push("Live chart unavailable");
        if (predictionResp.status === "rejected") messages.push("Prediction unavailable");
        if (messages.length === 3) setError(messages.join(" · "));
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load stock stream");
      } finally {
        if (mounted) setLoading(false);
      }
    }

    bootstrap();

    const ws = createStockSocket(ticker, (tick) => {
      setLatest(tick);
      setHistory((prev) => upsertFromTick(prev, tick, range));
      if (tick.prediction) {
        setPrediction(tick.prediction);
      }
    });
    wsRef.current = ws;

    return () => {
      mounted = false;
      ws.close();
      wsRef.current = null;
    };
    }, [ticker, range]);

  const lastUpdated = useMemo(() => {
    if (!latest?.timestamp) return "-";
    return new Date(latest.timestamp).toLocaleTimeString();
  }, [latest]);

  return { latest, history, prediction, loading, error, lastUpdated };
}
