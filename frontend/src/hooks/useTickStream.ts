import { useEffect, useMemo, useRef } from "react";
import { createStockSocket } from "../services/websocket";
import { getLatestStock } from "../services/api";
import { usePortfolioStore } from "../store/portfolio";

type TickRow = {
  price: number;
  open: number;
  timestamp: string;
};

export function useTickStream(symbols: string[]) {
  const setLatestPrice = usePortfolioStore((s) => s.setLatestPrice);
  const rafRef = useRef<number | null>(null);
  const queueRef = useRef<Record<string, TickRow>>({});

  const uniqueSymbols = useMemo(
    () => Array.from(new Set(symbols.map((s) => s.toUpperCase().trim()).filter(Boolean))),
    [symbols]
  );

  useEffect(() => {
    let stopped = false;
    const sockets: WebSocket[] = [];

    const flush = () => {
      const rows = queueRef.current;
      queueRef.current = {};
      Object.entries(rows).forEach(([symbol, row]) => setLatestPrice(symbol, row));
      rafRef.current = null;
    };

    const queue = (symbol: string, row: TickRow) => {
      queueRef.current[symbol] = row;
      if (rafRef.current == null) {
        rafRef.current = window.requestAnimationFrame(flush);
      }
    };

    const bootstrap = async () => {
      await Promise.all(
        uniqueSymbols.map(async (symbol) => {
          try {
            const latest = await getLatestStock(symbol);
            queue(symbol, {
              price: Number(latest.price || 0),
              open: Number(latest.open_price || latest.price || 0),
              timestamp: latest.timestamp
            });
          } catch {
            // Keep stream resilient.
          }
        })
      );

      if (stopped) return;

      uniqueSymbols.forEach((symbol) => {
        const ws = createStockSocket(symbol, (tick) => {
          queue(symbol, {
            price: Number(tick.price || 0),
            open: Number(tick.open_price || tick.price || 0),
            timestamp: tick.timestamp
          });
        });
        sockets.push(ws);
      });
    };

    void bootstrap();

    return () => {
      stopped = true;
      sockets.forEach((ws) => ws.close());
      if (rafRef.current != null) {
        window.cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
      queueRef.current = {};
    };
  }, [setLatestPrice, uniqueSymbols]);
}
