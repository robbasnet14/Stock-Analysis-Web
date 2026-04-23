import { useEffect, useMemo, useState } from "react";
import { searchStocks } from "../../services/api";

type SearchRow = {
  symbol: string;
  display_symbol: string;
  description: string;
  type: string;
};

export function TickerSearch({ onSelect }: { onSelect: (symbol: string) => void }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchRow[]>([]);

  useEffect(() => {
    const q = query.trim();
    if (q.length < 1) {
      setResults([]);
      return;
    }
    const t = window.setTimeout(async () => {
      try {
        const rows = await searchStocks(q);
        setResults(rows.slice(0, 8));
      } catch {
        setResults([]);
      }
    }, 250);

    return () => window.clearTimeout(t);
  }, [query]);

  const hasResults = useMemo(() => results.length > 0, [results.length]);

  return (
    <div className="relative w-full max-w-md">
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value.toUpperCase())}
        placeholder="Search ticker (AAPL, NVDA...)"
        className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-cyan-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
      />
      {hasResults ? (
        <div className="absolute z-20 mt-1 max-h-64 w-full overflow-auto rounded-md border border-slate-300 bg-white/95 p-1 shadow-lg dark:border-slate-700 dark:bg-slate-950/95">
          {results.map((r) => (
            <button
              key={`${r.symbol}-${r.type}`}
              type="button"
              onClick={() => {
                setQuery(r.symbol);
                setResults([]);
                onSelect(r.symbol);
              }}
              className="flex w-full items-center justify-between rounded px-2 py-2 text-left text-sm hover:bg-slate-100 dark:hover:bg-slate-800"
            >
              <span className="font-semibold">{r.symbol}</span>
              <span className="truncate pl-3 text-xs text-slate-500 dark:text-slate-400">{r.description}</span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
