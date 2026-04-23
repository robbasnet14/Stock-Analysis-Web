import { useEffect, useState } from "react";
import { getNews } from "../services/api";
import { NewsArticle } from "../types";

const wsBase = (import.meta.env.VITE_WS_BASE_URL ?? "ws://localhost:8000").replace(/\/$/, "");

type NewsState = {
  items: NewsArticle[];
  averageSentiment: number;
  loading: boolean;
};

export function useNewsStream(ticker: string, refreshMs = 30000): NewsState {
  const [items, setItems] = useState<NewsArticle[]>([]);
  const [averageSentiment, setAverageSentiment] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    let ws: WebSocket | null = null;

    const load = async () => {
      try {
        const data = await getNews(ticker);
        if (!mounted) return;
        setItems(data.articles);
        setAverageSentiment(data.average_sentiment);
      } catch {
        if (!mounted) return;
        setItems([]);
        setAverageSentiment(0);
      } finally {
        if (mounted) setLoading(false);
      }
    };

    void load();

    try {
      ws = new WebSocket(`${wsBase}/ws/news?tickers=${encodeURIComponent(ticker.toUpperCase())}`);
      ws.onopen = () => {
        ws?.send(JSON.stringify({ tickers: [ticker.toUpperCase()] }));
      };
      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as any;
          if (payload?.type === "subscribed") return;
          if ((payload?.ticker || "").toUpperCase() !== ticker.toUpperCase()) return;
          if (Array.isArray(payload?.articles)) {
            setItems(payload.articles as NewsArticle[]);
          } else if (payload?.headline) {
            const next: NewsArticle = {
              ticker: payload.ticker || ticker.toUpperCase(),
              headline: payload.headline,
              summary: payload.summary || "",
              source: payload.source || "unknown",
              url: payload.url || "",
              sentiment_label: payload.sentiment_label || "neutral",
              sentiment_score: Number(payload.sentiment_score || 0),
              published_at: payload.published_at || new Date().toISOString()
            };
            setItems((prev) => {
              const merged = [next, ...prev];
              const dedup = new Map<string, NewsArticle>();
              merged.forEach((a) => dedup.set(`${a.url}|${a.headline}`, a));
              return Array.from(dedup.values()).slice(0, 100);
            });
          }
          if (typeof payload?.average_sentiment === "number") setAverageSentiment(payload.average_sentiment);
        } catch {
          // Ignore malformed frames.
        }
      };
    } catch {
      // Polling fallback continues.
    }

    const timer = window.setInterval(() => {
      void load();
    }, refreshMs);

    return () => {
      mounted = false;
      if (ws) ws.close();
      window.clearInterval(timer);
    };
  }, [refreshMs, ticker]);

  return { items, averageSentiment, loading };
}
