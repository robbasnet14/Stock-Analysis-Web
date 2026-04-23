import { MarketOverview } from "../models/types.js";
import { watchlistStore } from "../data/watchlistStore.js";
import { fetchNews, fetchQuotes } from "./marketDataService.js";
import { alertStore } from "./alertService.js";
import { buildTradeSetups, generateSignals } from "./signalEngine.js";

let snapshot: MarketOverview = {
  timestamp: new Date(0).toISOString(),
  watchlist: watchlistStore.getAll(),
  topBullCases: [],
  tradeSetups: [],
  alerts: [],
  news: []
};

export async function refreshMarketSnapshot(): Promise<MarketOverview> {
  const watchlist = watchlistStore.getAll();
  const [quotes, news] = await Promise.all([fetchQuotes(watchlist), fetchNews(watchlist)]);

  const topBullCases = generateSignals(quotes, news).slice(0, 12);
  const tradeSetups = buildTradeSetups(topBullCases);
  const alerts = alertStore.update(topBullCases, news);

  snapshot = {
    timestamp: new Date().toISOString(),
    watchlist,
    topBullCases,
    tradeSetups,
    alerts,
    news
  };

  return snapshot;
}

export function getSnapshot(): MarketOverview {
  return snapshot;
}
