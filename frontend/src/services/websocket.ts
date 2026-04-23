import { StockTick } from "../types";

const wsBase = (import.meta.env.VITE_WS_BASE_URL ?? "ws://localhost:8000").replace(/\/$/, "");

export function createStockSocket(ticker: string, onTick: (tick: StockTick) => void): WebSocket {
  const symbol = ticker.toUpperCase();
  const ws = new WebSocket(`${wsBase}/ws/stocks/${symbol}`);

  ws.onopen = () => {
    ws.send(JSON.stringify({ type: "subscribe", ticker: symbol }));
  };

  ws.onmessage = (event: MessageEvent) => {
    try {
      const payload = JSON.parse(event.data) as StockTick;
      onTick(payload);
    } catch {
      // ignore malformed frame
    }
  };

  return ws;
}

export function createOrderSocket(accessToken: string, onUpdate: (payload: { type: string; order: any }) => void): WebSocket {
  const url = `${wsBase}/ws/orders?token=${encodeURIComponent(accessToken)}`;
  const ws = new WebSocket(url);

  ws.onopen = () => {
    ws.send(JSON.stringify({ type: "subscribe_orders" }));
  };

  ws.onmessage = (event: MessageEvent) => {
    try {
      const payload = JSON.parse(event.data) as { type: string; order: any };
      onUpdate(payload);
    } catch {
      // ignore malformed frame
    }
  };

  return ws;
}
