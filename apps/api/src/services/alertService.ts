import { AlertEvent, BullCaseSignal, NewsItem } from "../models/types.js";

class AlertStore {
  private alerts: AlertEvent[] = [];

  update(signals: BullCaseSignal[], news: NewsItem[]): AlertEvent[] {
    const generated: AlertEvent[] = [];
    const now = new Date().toISOString();

    for (const signal of signals.slice(0, 8)) {
      if (signal.score >= 0.95 && signal.riskReward >= 1.8) {
        generated.push({
          id: `${signal.symbol}-bull-${Date.now()}`,
          symbol: signal.symbol,
          type: "bull_breakout",
          severity: "high",
          message: `${signal.symbol} bull case strengthened. Score ${signal.score}, R/R ${signal.riskReward}.`,
          createdAt: now
        });
      } else if (signal.volumeSpike >= 1.45) {
        generated.push({
          id: `${signal.symbol}-vol-${Date.now()}`,
          symbol: signal.symbol,
          type: "volume_spike",
          severity: "medium",
          message: `${signal.symbol} volume spike detected at ${signal.volumeSpike}x normal volume.`,
          createdAt: now
        });
      }
    }

    for (const item of news.slice(0, 4)) {
      if (item.sentimentScore >= 0.35 && item.symbols.length) {
        generated.push({
          id: `${item.id}-news`,
          symbol: item.symbols[0],
          type: "news_catalyst",
          severity: "medium",
          message: `${item.symbols[0]} positive catalyst: ${item.headline}`,
          createdAt: now
        });
      }
    }

    this.alerts = [...generated, ...this.alerts].slice(0, 40);
    return this.alerts;
  }

  list(): AlertEvent[] {
    return this.alerts;
  }
}

export const alertStore = new AlertStore();
