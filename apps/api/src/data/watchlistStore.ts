const DEFAULT_WATCHLIST = ["AAPL", "MSFT", "NVDA", "AMZN", "TSLA", "META", "AMD", "GOOGL"];

class WatchlistStore {
  private symbols = new Set<string>(DEFAULT_WATCHLIST);

  getAll(): string[] {
    return Array.from(this.symbols);
  }

  add(symbol: string): string[] {
    this.symbols.add(symbol.toUpperCase());
    return this.getAll();
  }

  remove(symbol: string): string[] {
    this.symbols.delete(symbol.toUpperCase());
    return this.getAll();
  }
}

export const watchlistStore = new WatchlistStore();
