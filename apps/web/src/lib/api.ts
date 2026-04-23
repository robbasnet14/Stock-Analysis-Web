import { ChatMessage, MarketOverview } from "../types/api";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:4000/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    headers: {
      "Content-Type": "application/json"
    },
    ...options
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "Request failed");
  }

  return (await response.json()) as T;
}

export function fetchOverview(): Promise<MarketOverview> {
  return request<MarketOverview>("/overview");
}

export function refreshOverview(): Promise<MarketOverview> {
  return request<MarketOverview>("/refresh");
}

export function addToWatchlist(symbol: string): Promise<{ watchlist: string[] }> {
  return request("/watchlist", {
    method: "POST",
    body: JSON.stringify({ symbol })
  });
}

export function removeFromWatchlist(symbol: string): Promise<{ watchlist: string[] }> {
  return request("/watchlist", {
    method: "DELETE",
    body: JSON.stringify({ symbol })
  });
}

export function chat(messages: ChatMessage[]): Promise<{ reply: string }> {
  return request<{ reply: string }>("/chat", {
    method: "POST",
    body: JSON.stringify({ messages })
  });
}
