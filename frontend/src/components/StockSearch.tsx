import { FormEvent, useEffect, useState } from "react";
import { searchStocks } from "../services/api";

interface Props {
  onSelect: (ticker: string) => void;
}

export function StockSearch({ onSelect }: Props) {
  const [value, setValue] = useState("TSLA");
  const [suggestions, setSuggestions] = useState<Array<{ symbol: string; description: string }>>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const q = value.trim();
    if (q.length < 1) {
      setSuggestions([]);
      return;
    }
    const t = window.setTimeout(() => {
      searchStocks(q)
        .then((rows) => {
          setSuggestions(rows.map((r) => ({ symbol: r.symbol, description: r.description })));
        })
        .catch(() => setSuggestions([]));
    }, 220);
    return () => window.clearTimeout(t);
  }, [value]);

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!value.trim()) return;
    onSelect(value.trim().toUpperCase());
    setOpen(false);
  }

  return (
    <div className="relative">
      <form onSubmit={submit} className="flex items-center gap-2">
        <input
          value={value}
          onFocus={() => setOpen(true)}
          onChange={(e) => setValue(e.target.value)}
          className="w-48 rounded-md border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-slate-100"
          placeholder="Search ticker"
        />
        <button className="rounded-md bg-cyan-500 px-3 py-2 text-sm font-medium text-slate-950 hover:bg-cyan-400">Search</button>
      </form>
      {open && suggestions.length ? (
        <div className="absolute z-20 mt-1 max-h-72 w-[320px] overflow-auto rounded-md border border-slate-700 bg-slate-950 p-1 text-xs text-slate-200 shadow-lg">
          {suggestions.slice(0, 12).map((s) => (
            <button
              key={`${s.symbol}-${s.description}`}
              type="button"
              onClick={() => {
                setValue(s.symbol);
                onSelect(s.symbol);
                setOpen(false);
              }}
              className="flex w-full items-center justify-between rounded px-2 py-2 text-left hover:bg-slate-800"
            >
              <span className="font-semibold">{s.symbol}</span>
              <span className="ml-2 truncate text-slate-400">{s.description}</span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
