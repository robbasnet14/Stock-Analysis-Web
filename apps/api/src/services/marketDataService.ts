import { Quote, NewsItem } from "../models/types.js";
import { config } from "../config.js";
import { round, clamp } from "../utils/math.js";

async function safeFetch<T>(url: string): Promise<T | null> {
  try {
    const response = await fetch(url);
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

function fallbackQuote(symbol: string): Quote {
  const base = 90 + Math.random() * 350;
  const changePercent = (Math.random() - 0.4) * 4;
  const price = base * (1 + changePercent / 100);
  const volume = Math.round(4_000_000 + Math.random() * 30_000_000);
  const avgVolume = Math.round(5_000_000 + Math.random() * 25_000_000);

  return {
    symbol,
    price: round(price),
    changePercent: round(changePercent),
    high: round(price * 1.015),
    low: round(price * 0.985),
    volume,
    avgVolume,
    lastUpdated: new Date().toISOString()
  };
}

async function fetchFinnhubQuote(symbol: string): Promise<Quote | null> {
  if (!config.finnhubApiKey) {
    return null;
  }

  const url = `https://finnhub.io/api/v1/quote?symbol=${symbol}&token=${config.finnhubApiKey}`;
  const data = await safeFetch<{ c: number; dp: number; h: number; l: number }>(url);

  if (!data?.c) {
    return null;
  }

  const syntheticVolume = Math.round(5_000_000 + Math.random() * 35_000_000);
  const syntheticAvgVolume = Math.round(6_000_000 + Math.random() * 30_000_000);

  return {
    symbol,
    price: round(data.c),
    changePercent: round(data.dp),
    high: round(data.h),
    low: round(data.l),
    volume: syntheticVolume,
    avgVolume: syntheticAvgVolume,
    lastUpdated: new Date().toISOString()
  };
}

async function fetchYahooQuote(symbol: string): Promise<Quote | null> {
  const url = `https://query1.finance.yahoo.com/v7/finance/quote?symbols=${symbol}`;
  const data = await safeFetch<{
    quoteResponse?: {
      result?: Array<{
        regularMarketPrice: number;
        regularMarketChangePercent: number;
        regularMarketDayHigh: number;
        regularMarketDayLow: number;
        regularMarketVolume: number;
        averageDailyVolume3Month: number;
      }>;
    };
  }>(url);

  const item = data?.quoteResponse?.result?.[0];
  if (!item?.regularMarketPrice) {
    return null;
  }

  return {
    symbol,
    price: round(item.regularMarketPrice),
    changePercent: round(item.regularMarketChangePercent ?? 0),
    high: round(item.regularMarketDayHigh ?? item.regularMarketPrice),
    low: round(item.regularMarketDayLow ?? item.regularMarketPrice),
    volume: item.regularMarketVolume ?? 0,
    avgVolume: item.averageDailyVolume3Month ?? item.regularMarketVolume ?? 0,
    lastUpdated: new Date().toISOString()
  };
}

export async function fetchQuotes(symbols: string[]): Promise<Quote[]> {
  const quotePromises = symbols.map(async (symbol) => {
    const normalized = symbol.toUpperCase();
    const fromFinnhub = await fetchFinnhubQuote(normalized);
    if (fromFinnhub) {
      return fromFinnhub;
    }

    const fromYahoo = await fetchYahooQuote(normalized);
    if (fromYahoo) {
      return fromYahoo;
    }

    return fallbackQuote(normalized);
  });

  return Promise.all(quotePromises);
}

function inferSentiment(text: string): number {
  const positiveWords = ["beat", "growth", "up", "record", "bull", "surge", "upgrade", "strong"];
  const negativeWords = ["miss", "down", "fraud", "probe", "downgrade", "weak", "loss", "drop"];
  const t = text.toLowerCase();

  let score = 0;
  for (const word of positiveWords) {
    if (t.includes(word)) score += 0.15;
  }
  for (const word of negativeWords) {
    if (t.includes(word)) score -= 0.15;
  }

  return clamp(score, -1, 1);
}

function fallbackNews(symbols: string[]): NewsItem[] {
  return symbols.slice(0, 8).map((symbol, index) => ({
    id: `${symbol}-${index}`,
    headline: `${symbol} sees institutional positioning and elevated momentum activity`,
    summary:
      "Synthetic fallback headline. Connect Finnhub/Polygon/AlphaVantage keys for fully live institutional and options flow context.",
    source: "Quant Feed (Fallback)",
    url: `https://finance.yahoo.com/quote/${symbol}`,
    publishedAt: new Date(Date.now() - index * 15 * 60_000).toISOString(),
    sentimentScore: 0.2,
    symbols: [symbol]
  }));
}

async function fetchFinnhubNews(symbol: string): Promise<NewsItem[]> {
  if (!config.finnhubApiKey) {
    return [];
  }

  const today = new Date();
  const from = new Date(Date.now() - 3 * 24 * 60 * 60_000);

  const toISO = today.toISOString().slice(0, 10);
  const fromISO = from.toISOString().slice(0, 10);
  const url = `https://finnhub.io/api/v1/company-news?symbol=${symbol}&from=${fromISO}&to=${toISO}&token=${config.finnhubApiKey}`;

  const data = await safeFetch<
    Array<{
      id: number;
      headline: string;
      summary: string;
      source: string;
      url: string;
      datetime: number;
    }>
  >(url);

  if (!data?.length) {
    return [];
  }

  return data.slice(0, 3).map((item) => ({
    id: String(item.id),
    headline: item.headline,
    summary: item.summary,
    source: item.source,
    url: item.url,
    publishedAt: new Date(item.datetime * 1000).toISOString(),
    sentimentScore: inferSentiment(`${item.headline} ${item.summary}`),
    symbols: [symbol]
  }));
}

export async function fetchNews(symbols: string[]): Promise<NewsItem[]> {
  const bySymbol = await Promise.all(symbols.slice(0, 6).map((symbol) => fetchFinnhubNews(symbol)));
  const flattened = bySymbol.flat().sort((a, b) => +new Date(b.publishedAt) - +new Date(a.publishedAt));

  if (flattened.length > 0) {
    return flattened.slice(0, 12);
  }

  return fallbackNews(symbols);
}
