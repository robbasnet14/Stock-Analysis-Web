import { useSyncExternalStore } from "react";
import { Position } from "../types";

type LatestPrice = {
  price: number;
  open: number;
  timestamp: string;
};

type PortfolioState = {
  holdings: Position[];
  latestPrices: Record<string, LatestPrice>;
  signalTickers: string[];
};

const state: PortfolioState = {
  holdings: [],
  latestPrices: {},
  signalTickers: []
};

const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((l) => l());
}

function setHoldings(holdings: Position[]) {
  state.holdings = holdings;
  emit();
}

function setLatestPrice(symbol: string, value: LatestPrice) {
  state.latestPrices = { ...state.latestPrices, [symbol.toUpperCase()]: value };
  emit();
}

function setLatestBulk(rows: Record<string, LatestPrice>) {
  state.latestPrices = { ...state.latestPrices, ...rows };
  emit();
}

function removeHolding(positionId: number) {
  state.holdings = state.holdings.filter((h) => h.id !== positionId);
  emit();
}

function setSignalTickers(tickers: string[]) {
  state.signalTickers = Array.from(new Set(tickers.map((t) => t.trim().toUpperCase()).filter(Boolean)));
  emit();
}

function addSignalTicker(ticker: string) {
  const normalized = ticker.trim().toUpperCase();
  if (!normalized || state.signalTickers.includes(normalized)) {
    return;
  }
  state.signalTickers = [...state.signalTickers, normalized];
  emit();
}

function removeSignalTicker(ticker: string) {
  const normalized = ticker.trim().toUpperCase();
  state.signalTickers = state.signalTickers.filter((t) => t !== normalized);
  emit();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot() {
  return state;
}

type StoreApi = {
  setHoldings: typeof setHoldings;
  setLatestPrice: typeof setLatestPrice;
  setLatestBulk: typeof setLatestBulk;
  removeHolding: typeof removeHolding;
  setSignalTickers: typeof setSignalTickers;
  addSignalTicker: typeof addSignalTicker;
  removeSignalTicker: typeof removeSignalTicker;
};

const api: StoreApi = {
  setHoldings,
  setLatestPrice,
  setLatestBulk,
  removeHolding,
  setSignalTickers,
  addSignalTicker,
  removeSignalTicker
};

export function usePortfolioStore<T>(selector: (s: PortfolioState & StoreApi) => T): T {
  return useSyncExternalStore(subscribe, () => selector({ ...state, ...api }));
}

export type { LatestPrice, PortfolioState };
