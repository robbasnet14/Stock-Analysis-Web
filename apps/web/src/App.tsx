import { useEffect, useMemo, useState } from "react";
import { AlertStream } from "./components/AlertStream";
import { BullCaseBoard } from "./components/BullCaseBoard";
import { ChatBox } from "./components/ChatBox";
import { MetricStrip } from "./components/MetricStrip";
import { NewsPanel } from "./components/NewsPanel";
import { TradeSetupsTable } from "./components/TradeSetupsTable";
import { WatchlistManager } from "./components/WatchlistManager";
import { addToWatchlist, chat, fetchOverview, refreshOverview, removeFromWatchlist } from "./lib/api";
import { usePolling } from "./hooks/usePolling";
import { ChatMessage, MarketOverview } from "./types/api";

const emptyOverview: MarketOverview = {
  timestamp: new Date(0).toISOString(),
  watchlist: [],
  topBullCases: [],
  tradeSetups: [],
  alerts: [],
  news: []
};

const starterMessage: ChatMessage = {
  role: "assistant",
  content:
    "Ask me about any stock and I will break down bull case probability, entry, stop, target, and risk based on the live snapshot."
};

export default function App() {
  const [overview, setOverview] = useState<MarketOverview>(emptyOverview);
  const [loading, setLoading] = useState(true);
  const [chatLoading, setChatLoading] = useState(false);
  const [error, setError] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([starterMessage]);

  async function load(initial = false) {
    try {
      setError("");
      const data = initial ? await fetchOverview() : await refreshOverview();
      setOverview(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to fetch data";
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load(true);
  }, []);

  usePolling(() => {
    void load();
  }, 30_000);

  async function handleAddSymbol(symbol: string) {
    await addToWatchlist(symbol);
    await load();
  }

  async function handleRemoveSymbol(symbol: string) {
    await removeFromWatchlist(symbol);
    await load();
  }

  async function handleSendChat(prompt: string) {
    const nextMessages: ChatMessage[] = [...messages, { role: "user", content: prompt }];
    setMessages(nextMessages);
    setChatLoading(true);

    try {
      const response = await chat(nextMessages);
      setMessages((prev) => [...prev, { role: "assistant", content: response.reply }]);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Chat failed";
      setMessages((prev) => [...prev, { role: "assistant", content: `Error: ${message}` }]);
    } finally {
      setChatLoading(false);
    }
  }

  const metrics = useMemo(() => {
    const strongest = overview.topBullCases[0];
    const avgRR = overview.tradeSetups.length
      ? overview.tradeSetups.reduce((acc, s) => acc + s.riskReward, 0) / overview.tradeSetups.length
      : 0;

    return [
      { label: "Top Signal", value: strongest ? `${strongest.symbol} (${strongest.score})` : "-", tone: "good" as const },
      { label: "Avg Risk/Reward", value: avgRR ? avgRR.toFixed(2) : "-", tone: avgRR >= 1.5 ? "good" as const : "warn" as const },
      { label: "Live Alerts", value: String(overview.alerts.length), tone: overview.alerts.length ? "warn" as const : "neutral" as const },
      { label: "Watchlist", value: String(overview.watchlist.length), tone: "neutral" as const }
    ];
  }, [overview]);

  return (
    <main className="app-shell">
      <header className="hero">
        <p className="kicker">Quant Market Workbench</p>
        <h1>Live Bull Cases, Trade Entries, Alerts, and Quant Chat</h1>
        <p>
          System scans momentum, volume, news sentiment, and insider-style activity proxies to suggest high-conviction long and short-term
          opportunities.
        </p>
        <div className="hero-meta">
          <span>Last update: {new Date(overview.timestamp).toLocaleTimeString()}</span>
          <button onClick={() => load()} disabled={loading}>
            {loading ? "Loading..." : "Refresh now"}
          </button>
        </div>
      </header>

      {error ? <p className="error-banner">{error}</p> : null}

      <MetricStrip items={metrics} />

      <section className="grid-two">
        <BullCaseBoard signals={overview.topBullCases} />
        <WatchlistManager watchlist={overview.watchlist} onAdd={handleAddSymbol} onRemove={handleRemoveSymbol} />
      </section>

      <section className="grid-two">
        <TradeSetupsTable setups={overview.tradeSetups} />
        <AlertStream alerts={overview.alerts} />
      </section>

      <section className="grid-two">
        <NewsPanel news={overview.news} />
        <ChatBox messages={messages} onSend={handleSendChat} loading={chatLoading} />
      </section>
    </main>
  );
}
