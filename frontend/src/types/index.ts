export interface StockTick {
  ticker: string;
  price: number;
  change_percent: number;
  volume: number;
  open_price: number;
  high_price: number;
  low_price: number;
  timestamp: string;
  prediction?: Prediction;
}

export interface PricePoint {
  price: number;
  volume: number;
  change_percent: number;
  open_price: number;
  high_price: number;
  low_price: number;
  timestamp: string;
}

export interface NewsArticle {
  ticker: string;
  headline: string;
  summary: string;
  source: string;
  url: string;
  sentiment_label: "positive" | "neutral" | "negative" | string;
  sentiment_score: number;
  published_at: string;
}

export interface Prediction {
  ticker: string;
  bull_probability: number;
  bear_probability: number;
  reasons: string[];
  generated_at: string;
}

export interface TrendingItem {
  ticker: string;
  price: number;
  change_percent: number;
  volume: number;
  timestamp: string;
}

export interface BullCaseItem {
  ticker: string;
  price: number;
  change_percent: number;
  momentum_percent: number;
  volume_ratio: number;
  score: number;
  horizon?: "short" | "mid" | "long" | string;
  reasons: string[];
  timestamp: string;
}

export interface MarketPulseRow {
  symbol: string;
  price: number;
  change_percent: number;
}

export interface MarketPulse {
  indices: Record<string, MarketPulseRow>;
  top_gainers: MarketPulseRow[];
  top_losers: MarketPulseRow[];
  unusual_volume: Array<{ symbol: string; price: number; volume_ratio: number; change_percent: number }>;
  as_of: string;
}

export interface WatchlistIntelItem {
  symbol: string;
  price: number;
  change_percent: number;
  sentiment: "positive" | "neutral" | "negative" | string;
  momentum: "bullish" | "neutral" | "bearish" | string;
  analyst_rating: "buy" | "hold" | "sell" | string;
  risk_level: "low" | "medium" | "high" | string;
  volume_ratio: number;
  as_of: string;
}

export interface UserProfile {
  id: number;
  email: string;
  role: "admin" | "trader" | "viewer" | string;
  telegram_chat_id: string;
  first_name?: string;
  last_name?: string;
}

export interface Position {
  id: number;
  ticker: string;
  quantity: number;
  avg_cost: number;
  updated_at: string;
}

export interface PaperOrder {
  id: number;
  ticker: string;
  side: string;
  quantity: number;
  order_type: string;
  requested_price: number;
  filled_price: number;
  status: string;
  broker_mode: string;
  broker_order_id: string;
  created_at: string;
}

export interface BrokerAccountSummary {
  broker_mode: string;
  equity?: number;
  buying_power?: number;
  cash?: number;
  portfolio_value?: number;
  account_status?: string;
  message?: string;
}

export interface AdminUser {
  id: number;
  email: string;
  role: "admin" | "trader" | "viewer" | string;
  telegram_chat_id: string;
  created_at: string;
}

export interface LiveDataStatus {
  live_data_only: boolean;
  finnhub_configured: boolean;
  provider: string;
  providers_configured?: Record<string, boolean>;
}

export interface MarketSessionStatus {
  session: "premarket" | "market" | "after-hours" | "closed" | string;
  is_open: boolean;
  timestamp: string;
  exchange_tz?: string;
  server_time?: string;
}

export interface ProviderHealthItem {
  configured: boolean;
  last_ok: string | null;
  last_error: string | null;
  last_latency_ms: number | null;
  last_checked: string | null;
  successes: number;
  failures: number;
}

export interface ProviderStatusResponse {
  checked_at: string;
  providers: Record<string, ProviderHealthItem>;
}

export interface CacheHealthResponse {
  ok: boolean;
  redis_connected: boolean;
  latency_ms?: number;
  db_keys?: number;
  error?: string;
}

export interface SignalRule {
  rule: string;
  value: number;
  vote: number;
  weight: number;
  fired: boolean;
  explanation: string;
}

export interface SignalVerdict {
  label: "BULLISH" | "BEARISH" | "NEUTRAL" | string;
  score: number;
  confidence: number;
  track: "technical" | "ensemble" | string;
}

export interface SignalDetailResponse {
  ticker: string;
  company_name: string;
  asset_class: string;
  quote: {
    price: number;
    change: number;
    change_percent: number;
  };
  horizon: "short" | "mid" | "long" | string;
  verdict: SignalVerdict;
  triggered_rules: SignalRule[];
  projection: {
    median_return_pct: number | null;
    bullish_case_pct: number | null;
    bearish_case_pct: number | null;
    projected_price_median: number | null;
    projected_price_bull: number | null;
    projected_price_bear: number | null;
    accuracy_pct: number;
    sample_size: number;
    backtest_start: string | null;
    backtest_end: string | null;
  };
  news: {
    sentiment_score: number;
    article_count_24h: number;
    top_articles: Array<{
      title: string;
      source: string;
      published_at: string;
      sentiment: string;
      url: string;
    }>;
  };
  context?: {
    regime: "risk_on" | "neutral" | "risk_off" | "transitional" | string;
    regime_context?: {
      spy_above_200ema?: boolean;
      vix?: number;
      signal_modifier?: number;
    };
    sector?: string | null;
    sector_position: "leading" | "lagging" | "neutral" | string;
    next_earnings?: {
      date: string;
      hour?: string | null;
      epsEstimate?: number | null;
      revenueEstimate?: number | null;
    } | null;
    matched_themes: Array<{ theme: string; sentiment: number }>;
    extras: string[];
  };
  levels: {
    current: number;
    support: number;
    resistance: number;
    suggested_stop: number;
    suggested_take_profit: number;
    risk_reward_ratio: number;
  };
  mini_chart_bars: Array<{
    timestamp: string;
    close: number;
  }>;
  signals: {
    technical: {
      verdict: SignalVerdict;
      triggered_rules: SignalRule[];
      explanation: string;
    };
    ensemble: {
      verdict: SignalVerdict;
      triggered_rules: SignalRule[];
      explanation: string;
    };
  };
}
