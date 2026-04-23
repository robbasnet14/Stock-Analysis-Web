import { BullCaseSignal, NewsItem, Quote, TradeSetup } from "../models/types.js";
import { clamp, round } from "../utils/math.js";

function buildRationale(signal: BullCaseSignal): string[] {
  const notes: string[] = [];

  if (signal.momentum > 0.5) {
    notes.push("Momentum regime is bullish across recent sessions.");
  }
  if (signal.volumeSpike > 1.2) {
    notes.push("Volume is above baseline, showing conviction from buyers.");
  }
  if (signal.sentiment > 0.2) {
    notes.push("Recent news sentiment supports upside continuation.");
  }
  if (signal.insiderActivityScore > 0.45) {
    notes.push("Insider/institutional proxy score is elevated.");
  }
  if (!notes.length) {
    notes.push("Mixed setup: wait for stronger catalyst confirmation.");
  }

  return notes;
}

export function generateSignals(quotes: Quote[], news: NewsItem[]): BullCaseSignal[] {
  const newsBySymbol = new Map<string, NewsItem[]>();
  for (const item of news) {
    for (const symbol of item.symbols) {
      const prev = newsBySymbol.get(symbol) ?? [];
      prev.push(item);
      newsBySymbol.set(symbol, prev);
    }
  }

  return quotes
    .map((quote) => {
      const sentimentItems = newsBySymbol.get(quote.symbol) ?? [];
      const sentimentRaw = sentimentItems.reduce((acc, n) => acc + n.sentimentScore, 0) / (sentimentItems.length || 1);

      const momentum = clamp((quote.changePercent + 5) / 10, 0, 1.2);
      const volumeSpike = clamp(quote.volume / Math.max(quote.avgVolume, 1), 0.2, 3);
      const sentiment = clamp((sentimentRaw + 1) / 2, 0, 1);
      const insiderActivityScore = clamp(0.25 + volumeSpike * 0.2 + Math.max(0, quote.changePercent) * 0.03, 0, 1);
      const score = clamp(momentum * 0.35 + volumeSpike * 0.25 + sentiment * 0.2 + insiderActivityScore * 0.2, 0, 1.5);
      const confidence = clamp(score * 0.8 + 0.15, 0, 1);

      const entry = quote.price;
      const stopLoss = round(entry * (1 - (0.02 + (1 - confidence) * 0.04)));
      const target = round(entry * (1 + (0.03 + confidence * 0.08)));
      const riskReward = round((target - entry) / Math.max(entry - stopLoss, 0.01));

      const horizon: "short" | "long" = momentum >= 0.55 ? "short" : "long";

      const signal: BullCaseSignal = {
        symbol: quote.symbol,
        score: round(score),
        confidence: round(confidence),
        momentum: round(momentum),
        volumeSpike: round(volumeSpike),
        sentiment: round(sentiment),
        insiderActivityScore: round(insiderActivityScore),
        entry: round(entry),
        target,
        stopLoss,
        riskReward,
        horizon,
        updatedAt: new Date().toISOString(),
        notes: []
      };

      signal.notes = buildRationale(signal);
      return signal;
    })
    .sort((a, b) => b.score - a.score);
}

export function buildTradeSetups(signals: BullCaseSignal[]): TradeSetup[] {
  return signals.slice(0, 10).map((signal) => ({
    symbol: signal.symbol,
    horizon: signal.horizon,
    entry: signal.entry,
    stopLoss: signal.stopLoss,
    target: signal.target,
    riskReward: signal.riskReward,
    confidence: signal.confidence,
    rationale: signal.notes
  }));
}
