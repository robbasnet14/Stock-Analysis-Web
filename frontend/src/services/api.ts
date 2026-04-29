import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";
import { clearTokens, getAccessToken, getRefreshToken, isAuthenticated, setTokens } from "./auth";
import { AdminUser, AlertChannel, AlertConditionType, AlertFire, AlertSubscription, BrokerAccountSummary, BullCaseItem, CacheHealthResponse, LiveDataStatus, MarketPulse, MarketSessionStatus, NewsArticle, PaperOrder, Position, Prediction, PricePoint, ProviderStatusResponse, SignalDetailResponse, StockTick, TrendingItem, UserProfile, WatchlistIntelItem } from "../types";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");

const api = axios.create({
  baseURL: API_BASE_URL
});

interface RetryConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const responseData = error.response?.data as { detail?: string; message?: string } | string | undefined;
    if (typeof responseData === "string" && responseData.trim()) {
      return responseData;
    }
    if (responseData && typeof responseData === "object") {
      if (typeof responseData.detail === "string" && responseData.detail.trim()) {
        return responseData.detail;
      }
      if (typeof responseData.message === "string" && responseData.message.trim()) {
        return responseData.message;
      }
    }
  }

  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }

  return fallback;
}

function isUnauthorized(error: unknown): boolean {
  return axios.isAxiosError(error) && error.response?.status === 401;
}

function normalizeTickerList(data: unknown): string[] {
  if (Array.isArray(data)) {
    return data
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object") {
          const symbol = (item as { symbol?: string; ticker?: string }).symbol ?? (item as { symbol?: string; ticker?: string }).ticker;
          return typeof symbol === "string" ? symbol : null;
        }
        return null;
      })
      .filter((value): value is string => Boolean(value))
      .map((value) => value.toUpperCase());
  }

  if (data && typeof data === "object") {
    const watchlist = (data as { watchlist?: unknown }).watchlist;
    if (watchlist) {
      return normalizeTickerList(watchlist);
    }
  }

  return [];
}

function sanitizePricePoint(point: Partial<PricePoint> | null | undefined): PricePoint | null {
  if (!point || typeof point !== "object") return null;

  const timestamp = typeof point.timestamp === "string" ? point.timestamp : "";
  const parsed = Date.parse(timestamp);
  const price = Number(point.price);

  if (!timestamp || Number.isNaN(parsed) || !Number.isFinite(price) || price <= 0) {
    return null;
  }

  const open = Number(point.open_price);
  const high = Number(point.high_price);
  const low = Number(point.low_price);
  const volume = Number(point.volume);
  const changePercent = Number(point.change_percent);

  const normalizedOpen = Number.isFinite(open) && open > 0 ? open : price;
  const normalizedHigh = Number.isFinite(high) && high > 0 ? Math.max(high, normalizedOpen, price) : Math.max(normalizedOpen, price);
  const normalizedLow = Number.isFinite(low) && low > 0 ? Math.min(low, normalizedOpen, price) : Math.min(normalizedOpen, price);

  return {
    timestamp: new Date(parsed).toISOString(),
    price,
    volume: Number.isFinite(volume) && volume >= 0 ? volume : 0,
    change_percent: Number.isFinite(changePercent) ? changePercent : 0,
    open_price: normalizedOpen,
    high_price: normalizedHigh,
    low_price: normalizedLow
  };
}

function sanitizePriceSeries(data: unknown): PricePoint[] {
  if (!Array.isArray(data)) return [];

  const deduped = new Map<string, PricePoint>();

  data.forEach((row) => {
    const point = sanitizePricePoint(row as Partial<PricePoint>);
    if (!point) return;
    deduped.set(point.timestamp, point);
  });

  return Array.from(deduped.values()).sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp));
}

function dedupeArticles(articles: NewsArticle[]): NewsArticle[] {
  const seen = new Set<string>();

  return articles.filter((article) => {
    const key = `${article.url || ""}|${article.headline.trim().toLowerCase()}|${article.published_at}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

api.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) {
    config.headers = config.headers ?? {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as RetryConfig | undefined;
    const status = error.response?.status;

    if (!original || original._retry || status !== 401) {
      return Promise.reject(error);
    }

    const refresh = getRefreshToken();
    if (!refresh) {
      clearTokens();
      return Promise.reject(error);
    }

    original._retry = true;

    try {
      const { data } = await axios.post<{ access_token: string; refresh_token: string }>(`${API_BASE_URL}/api/auth/refresh`, {
        refresh_token: refresh
      });
      setTokens(data.access_token, data.refresh_token);
      original.headers = original.headers ?? {};
      original.headers.Authorization = `Bearer ${data.access_token}`;
      return api(original);
    } catch (refreshError) {
      clearTokens();
      return Promise.reject(refreshError);
    }
  }
);

export async function register(payload: {
  first_name: string;
  last_name: string;
  date_of_birth: string;
  email: string;
  password: string;
  password_confirm: string;
}): Promise<{ access_token: string; refresh_token: string }> {
  const { data } = await api.post<{ access_token: string; refresh_token: string }>("/api/auth/register", payload);
  return data;
}

export async function login(email: string, password: string): Promise<{ access_token: string; refresh_token: string }> {
  const { data } = await api.post<{ access_token: string; refresh_token: string }>("/api/auth/login", { email, password });
  return data;
}

export async function logout(): Promise<void> {
  const refresh = getRefreshToken();
  if (!refresh) return;
  try {
    await api.post("/api/auth/logout", { refresh_token: refresh });
  } finally {
    clearTokens();
  }
}

export async function me(): Promise<UserProfile> {
  const { data } = await api.get<UserProfile>("/api/auth/me");
  return data;
}

export async function setTelegramChatId(chatId: string): Promise<void> {
  await api.post(`/api/auth/telegram?chat_id=${encodeURIComponent(chatId)}`);
}

export async function getWatchlist(): Promise<string[]> {
  if (!isAuthenticated()) {
    return [];
  }

  const watchlistEndpoints = ["/api/watchlist", "/api/portfolio/watchlist"];

  for (const endpoint of watchlistEndpoints) {
    try {
      const { data } = await api.get(endpoint);
      return normalizeTickerList(data);
    } catch (error) {
      if (isUnauthorized(error)) {
        return [];
      }
    }
  }

  return [];
}

export async function searchStocks(q: string): Promise<Array<{ symbol: string; display_symbol: string; description: string; type: string }>> {
  const { data } = await api.get<{ results: Array<{ symbol: string; display_symbol: string; description: string; type: string }> }>(
    `/api/stocks/search?q=${encodeURIComponent(q)}`
  );
  return data.results;
}

export async function getLiveStatus(): Promise<LiveDataStatus> {
  const { data } = await api.get<LiveDataStatus>("/api/stocks/live-status");
  return data;
}

export async function getMarketSession(): Promise<MarketSessionStatus> {
  const { data } = await api.get<MarketSessionStatus>("/api/stocks/session");
  return data;
}

export async function addWatchlist(ticker: string): Promise<string[]> {
  if (!isAuthenticated()) {
    throw new Error("Sign in to save a personal watchlist.");
  }

  const normalized = ticker.trim().toUpperCase();
  const writeAttempts: Array<{ method: "post" | "delete"; url: string; data?: unknown }> = [
    { method: "post", url: "/api/watchlist/add", data: { symbol: normalized } },
    { method: "post", url: "/api/portfolio/watchlist", data: { ticker: normalized } },
    { method: "post", url: "/api/portfolio/watchlist", data: { symbol: normalized } }
  ];

  for (const attempt of writeAttempts) {
    try {
      if (attempt.method === "post") {
        await api.post(attempt.url, attempt.data);
      }
      return await getWatchlist();
    } catch (error) {
      if (isUnauthorized(error)) {
        throw new Error("Sign in to save a personal watchlist.");
      }
    }
  }

  throw new Error("Unable to update watchlist right now.");
}

export async function removeWatchlist(ticker: string): Promise<string[]> {
  if (!isAuthenticated()) {
    throw new Error("Sign in to edit your saved watchlist.");
  }

  const normalized = ticker.trim().toUpperCase();
  const writeAttempts = [
    `/api/watchlist/remove/${encodeURIComponent(normalized)}`,
    `/api/portfolio/watchlist/${encodeURIComponent(normalized)}`
  ];

  for (const endpoint of writeAttempts) {
    try {
      await api.delete(endpoint);
      return await getWatchlist();
    } catch (error) {
      if (isUnauthorized(error)) {
        throw new Error("Sign in to edit your saved watchlist.");
      }
    }
  }

  throw new Error("Unable to remove that watchlist item right now.");
}

export async function getLatestStock(ticker: string): Promise<StockTick> {
  const { data } = await api.get<StockTick>(`/api/stocks/${ticker}/latest`);
  return data;
}

export async function getHistory(ticker: string): Promise<PricePoint[]> {
  const { data } = await api.get<{ ticker: string; data: PricePoint[] }>(`/api/stocks/${ticker}/history?limit=180`);
  return sanitizePriceSeries(data.data);
}

export async function getCandles(ticker: string, range: "1D" | "1W" | "1M" | "3M" | "1Y" | "ALL"): Promise<PricePoint[]> {
  const { data } = await api.get<{ ticker: string; range: string; data: PricePoint[] }>(`/api/stocks/${ticker}/candles?range=${range}`);
  return sanitizePriceSeries(data.data);
}

export async function getNews(ticker: string): Promise<{ average_sentiment: number; articles: NewsArticle[] }> {
  const { data } = await api.get<{ ticker: string; average_sentiment: number; articles: NewsArticle[] }>(`/api/news/${ticker}`);
  const articles = Array.isArray(data.articles) ? data.articles : [];
  return {
    average_sentiment: Number.isFinite(data.average_sentiment) ? data.average_sentiment : 0,
    articles: dedupeArticles(articles)
  };
}

export async function getPrediction(ticker: string): Promise<Prediction> {
  const { data } = await api.get<Prediction>(`/api/predictions/${ticker}`);
  return data;
}

export async function getPredictionExplanation(ticker: string, horizon: "short" | "mid" | "long" = "short"): Promise<string> {
  const { data } = await api.get<{ explanation: string }>(`/api/predictions/${ticker}/llm-explanation?horizon=${encodeURIComponent(horizon)}`);
  return data.explanation;
}

export async function getTrending(): Promise<TrendingItem[]> {
  const { data } = await api.get<{ trending: TrendingItem[] }>("/api/stocks/trending/list");
  return data.trending;
}

export async function getBullCases(horizon: "short" | "mid" | "long" = "short"): Promise<BullCaseItem[]> {
  const { data } = await api.get<{ bull_cases: BullCaseItem[] }>(`/api/stocks/bull-cases/list?horizon=${encodeURIComponent(horizon)}`);
  return Array.isArray(data.bull_cases) ? data.bull_cases : [];
}

export async function getEnsembleDiagnostics(horizon: "short" | "mid" | "long" = "short"): Promise<Array<{ symbol: string; final_score: number; confidence?: number; confidence_band?: { low: number; base: number; high: number } }>> {
  const { data } = await api.get<Array<{ symbol: string; final_score: number; confidence?: number; confidence_band?: { low: number; base: number; high: number } }>>(
    `/api/stocks/ensemble-diagnostics?horizon=${encodeURIComponent(horizon)}`
  );
  return Array.isArray(data) ? data : [];
}

export async function getSignalBatch(
  track: "technical" | "ensemble",
  horizon: "short" | "mid" | "long" = "short",
  tickers: string[] = []
): Promise<unknown[]> {
  const q = encodeURIComponent(tickers.join(","));
  const { data } = await api.get<{ items: unknown[] }>(
    `/api/signals?track=${encodeURIComponent(track)}&horizon=${encodeURIComponent(horizon)}&tickers=${q}`
  );
  return Array.isArray(data.items) ? data.items : [];
}

export async function getTechnicalSnapshot(ticker: string): Promise<{ ticker: string; rsi: number; macd: number; signal_line: number; sma_20: number; sma_50: number }> {
  const { data } = await api.get<{ ticker: string; rsi: number; macd: number; signal_line: number; sma_20: number; sma_50: number }>(`/api/stocks/${encodeURIComponent(ticker)}/technical`);
  return data;
}

export async function getSignalDetail(ticker: string, horizon: "short" | "mid" | "long" = "short"): Promise<SignalDetailResponse> {
  const { data } = await api.get<SignalDetailResponse>(`/api/signals/detail/${encodeURIComponent(ticker)}?horizon=${encodeURIComponent(horizon)}`);
  return data;
}

export async function getMarketPulse(): Promise<MarketPulse> {
  const { data } = await api.get<MarketPulse>("/api/market/pulse");
  return data;
}

export async function getWatchlistIntelligence(): Promise<WatchlistIntelItem[]> {
  const { data } = await api.get<{ items: WatchlistIntelItem[] }>("/api/watchlist/intelligence");
  return data.items;
}

export async function getFlowSnapshot(ticker: string): Promise<{ dark_pool_volume: number; unusual_options_score: number; insider_bias_score: number; sources: string[] }> {
  const { data } = await api.get(`/api/providers/flow/${ticker}`);
  return data;
}

export async function getProviderStatus(): Promise<ProviderStatusResponse> {
  const { data } = await api.get<ProviderStatusResponse>("/api/providers/status");
  return data;
}

export async function getCacheHealth(): Promise<CacheHealthResponse> {
  const { data } = await api.get<CacheHealthResponse>("/api/providers/cache-health");
  return data;
}

export async function getPositions(): Promise<Position[]> {
  if (!isAuthenticated()) {
    return [];
  }

  try {
    const { data } = await api.get<Position[] | { positions?: Position[] }>("/api/portfolio/positions");
    if (Array.isArray(data)) {
      return data;
    }
    return Array.isArray(data.positions) ? data.positions : [];
  } catch (error) {
    if (isUnauthorized(error)) {
      return [];
    }
    throw new Error(getErrorMessage(error, "Unable to load portfolio positions."));
  }
}

export async function getHoldingLots(): Promise<Position[]> {
  if (!isAuthenticated()) {
    return [];
  }

  try {
    const { data } = await api.get<Position[]>("/api/portfolio/holdings");
    return Array.isArray(data) ? data : [];
  } catch (error) {
    if (isUnauthorized(error)) {
      return [];
    }
    throw new Error(getErrorMessage(error, "Unable to load holdings."));
  }
}

export async function getPortfolioValueHistory(range: "1D" | "1W" | "1M" | "3M" | "1Y" | "ALL"): Promise<PricePoint[]> {
  if (!isAuthenticated()) {
    return [];
  }

  try {
    const { data } = await api.get<{ range: string; data: PricePoint[] }>(`/api/portfolio/value-history?range=${range}`);
    return sanitizePriceSeries(data.data);
  } catch (error) {
    if (isUnauthorized(error)) {
      return [];
    }
    return [];
  }
}

export async function getPortfolioTimeseries(range: "1D" | "1W" | "1M" | "3M" | "1Y" | "ALL"): Promise<PricePoint[]> {
  if (!isAuthenticated()) {
    return [];
  }

  try {
    const { data } = await api.get<Array<{ time: number; value: number }>>(`/api/portfolio/timeseries?range=${range}`);
    return sanitizePriceSeries(
      data.map((point) => ({
        timestamp: new Date(Number(point.time) * 1000).toISOString(),
        price: Number(point.value),
        volume: 0,
        change_percent: 0,
        open_price: Number(point.value),
        high_price: Number(point.value),
        low_price: Number(point.value)
      }))
    );
  } catch (error) {
    if (isUnauthorized(error)) {
      return [];
    }
    return [];
  }
}

export async function getPortfolioHistory(range: "1D" | "1W" | "1M" | "3M" | "1Y" | "ALL"): Promise<PricePoint[]> {
  if (!isAuthenticated()) {
    return [];
  }

  try {
    const { data } = await api.get<{ range: string; data: PricePoint[] }>(`/api/portfolio/history?range=${range}`);
    return sanitizePriceSeries(data.data);
  } catch (error) {
    if (isUnauthorized(error)) {
      return [];
    }
    return [];
  }
}

export async function savePosition(ticker: string, quantity: number, avgCost: number): Promise<Position> {
  try {
    const { data } = await api.post<Position>("/api/portfolio/positions", { ticker, quantity, avg_cost: avgCost });
    return data;
  } catch (error) {
    throw new Error(getErrorMessage(error, "Unable to save position."));
  }
}

export async function saveHoldingLot(
  ticker: string,
  shares: number,
  buyPrice: number,
  buyTs?: string,
  mergeMode: "ask" | "merge" | "new_lot" = "ask"
): Promise<Position> {
  try {
    const { data } = await api.post<Position>("/api/portfolio/holdings", {
      ticker,
      shares,
      buy_price: buyPrice,
      buy_ts: buyTs,
      merge_mode: mergeMode
    });
    return data;
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 409) {
      const detail = error.response.data?.detail;
      const message = typeof detail?.message === "string" ? detail.message : "duplicate_ticker";
      throw new Error(message);
    }
    throw new Error(getErrorMessage(error, "Unable to save holding."));
  }
}

export async function updateHoldingLot(
  lotId: number,
  payload: { shares: number; buy_price: number; buy_ts?: string }
): Promise<{ removed: boolean; holding?: Position }> {
  try {
    const { data } = await api.patch<{ removed: boolean; holding?: Position }>(`/api/portfolio/holdings/${lotId}`, payload);
    return data;
  } catch (error) {
    throw new Error(getErrorMessage(error, "Unable to update holding."));
  }
}

export async function importPositionsCsv(file: File): Promise<{ imported_positions: number; lines_with_errors: number; errors: string[] }> {
  const form = new FormData();
  form.append("file", file);

  try {
    const { data } = await api.post<{ imported_positions: number; lines_with_errors: number; errors: string[] }>("/api/portfolio/import-csv", form, {
      headers: { "Content-Type": "multipart/form-data" }
    });
    return data;
  } catch (error) {
    throw new Error(getErrorMessage(error, "CSV import failed."));
  }
}

export async function deletePosition(id: number): Promise<void> {
  try {
    await api.delete(`/api/portfolio/positions/${id}`);
  } catch (error) {
    throw new Error(getErrorMessage(error, "Unable to delete position."));
  }
}

export async function deleteHoldingLot(id: number): Promise<void> {
  try {
    await api.delete(`/api/portfolio/holdings/${id}`);
  } catch (error) {
    throw new Error(getErrorMessage(error, "Unable to delete holding."));
  }
}

export async function placeOrder(payload: { ticker: string; side: "buy" | "sell"; quantity: number; order_type?: string; requested_price?: number }): Promise<void> {
  await api.post("/api/portfolio/orders", payload);
}

export async function listOrders(): Promise<PaperOrder[]> {
  const { data } = await api.get<{ orders: PaperOrder[] }>("/api/portfolio/orders");
  return data.orders;
}

export async function getBrokerAccount(): Promise<BrokerAccountSummary> {
  const { data } = await api.get<BrokerAccountSummary>("/api/broker/account");
  return data;
}

export async function listAdminUsers(): Promise<AdminUser[]> {
  const { data } = await api.get<{ users: AdminUser[] }>("/api/account/users");
  return data.users;
}

export async function setAdminUserRole(userId: number, role: "admin" | "trader" | "viewer"): Promise<void> {
  await api.post(`/api/account/users/${userId}/role?role=${encodeURIComponent(role)}`);
}

export async function listAlerts(): Promise<AlertSubscription[]> {
  if (!isAuthenticated()) return [];
  const { data } = await api.get<{ alerts: AlertSubscription[] }>("/api/alerts");
  return data.alerts;
}

export async function createAlert(payload: {
  ticker: string;
  condition_type: AlertConditionType;
  condition_params: Record<string, unknown>;
  channel: AlertChannel;
  enabled?: boolean;
}): Promise<AlertSubscription> {
  const { data } = await api.post<AlertSubscription>("/api/alerts", payload);
  return data;
}

export async function updateAlert(id: number, payload: { condition_params?: Record<string, unknown>; channel?: AlertChannel; enabled?: boolean }): Promise<AlertSubscription> {
  const { data } = await api.patch<AlertSubscription>(`/api/alerts/${id}`, payload);
  return data;
}

export async function deleteAlert(id: number): Promise<void> {
  await api.delete(`/api/alerts/${id}`);
}

export async function listAlertHistory(limit = 50): Promise<AlertFire[]> {
  if (!isAuthenticated()) return [];
  const { data } = await api.get<{ items: AlertFire[] }>(`/api/alerts/history?limit=${limit}`);
  return data.items;
}
