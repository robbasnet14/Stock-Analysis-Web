import { FormEvent, useState } from "react";

interface WatchlistManagerProps {
  watchlist: string[];
  onAdd: (symbol: string) => Promise<void>;
  onRemove: (symbol: string) => Promise<void>;
}

export function WatchlistManager({ watchlist, onAdd, onRemove }: WatchlistManagerProps) {
  const [symbol, setSymbol] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!symbol.trim()) return;
    await onAdd(symbol.trim().toUpperCase());
    setSymbol("");
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Watchlist</h2>
        <span>Track symbols for bull-case scanning</span>
      </div>
      <form className="watch-form" onSubmit={submit}>
        <input value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="Add symbol (e.g. PLTR)" />
        <button type="submit">Add</button>
      </form>
      <div className="watch-tags">
        {watchlist.map((item) => (
          <button key={item} className="tag" onClick={() => onRemove(item)}>
            {item} ×
          </button>
        ))}
      </div>
    </section>
  );
}
