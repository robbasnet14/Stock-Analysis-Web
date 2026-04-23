import { FormEvent, useState } from "react";

interface Props {
  items: string[];
  onAdd: (ticker: string) => Promise<void>;
  onRemove: (ticker: string) => Promise<void>;
  onSelect: (ticker: string) => void;
  selected: string;
}

export function Watchlist({ items, onAdd, onRemove, onSelect, selected }: Props) {
  const [input, setInput] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    const value = input.trim().toUpperCase();
    if (!value) return;
    await onAdd(value);
    setInput("");
  }

  return (
    <section className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-4">
      <h3 className="text-lg font-semibold text-slate-100">Watchlist</h3>
      <form onSubmit={submit} className="mt-3 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Add ticker"
          className="w-full rounded-md border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-slate-100"
        />
        <button className="rounded-md bg-cyan-500 px-3 py-2 text-sm font-medium text-slate-950 hover:bg-cyan-400">Add</button>
      </form>

      <div className="mt-3 flex flex-wrap gap-2">
        {items.map((ticker) => (
          <div
            key={ticker}
            className={`flex items-center gap-1 rounded-full border px-3 py-1 text-xs ${
              ticker === selected ? "border-cyan-400 bg-cyan-500/10 text-cyan-200" : "border-slate-600 text-slate-200"
            }`}
          >
            <button onClick={() => onSelect(ticker)}>{ticker}</button>
            <button onClick={() => onRemove(ticker)} className="text-slate-400 hover:text-rose-300">
              x
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}
