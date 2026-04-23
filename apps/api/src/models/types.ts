export type Horizon = "short" | "long";

export interface Quote {
  symbol: string;
  price: number;
  changePercent: number;
  volume: number;
  avgVolume: number;
  high: number;
  low: number;
  lastUpdated: string;
}

export interface NewsItem {
  id: string;
  headline: string;
  summary: string;
  source: string;
  url: string;
  publishedAt: string;
  sentimentScore: number;
  symbols: string[];
}

export interface TradeSetup {
  symbol: string;
  horizon: Horizon;
  entry: number;
  stopLoss: number;
  target: number;
  riskReward: number;
  confidence: number;
  rationale: string[];
}

export interface BullCaseSignal {
  symbol: string;
  score: number;
  confidence: number;
  momentum: number;
  volumeSpike: number;
  sentiment: number;
  insiderActivityScore: number;
  entry: number;
  target: number;
  stopLoss: number;
  riskReward: number;
  horizon: Horizon;
  updatedAt: string;
  notes: string[];
}

export interface AlertEvent {
  id: string;
  symbol: string;
  type: "bull_breakout" | "volume_spike" | "news_catalyst";
  severity: "low" | "medium" | "high";
  message: string;
  createdAt: string;
}

export interface MarketOverview {
  timestamp: string;
  watchlist: string[];
  topBullCases: BullCaseSignal[];
  tradeSetups: TradeSetup[];
  alerts: AlertEvent[];
  news: NewsItem[];
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}
